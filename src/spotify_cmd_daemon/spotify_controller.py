import os
import time
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from spotipy.exceptions import SpotifyException
from . import operations
from .operations.helpers import get_resource_uri
from .playback_session import PlaybackSession
from .device_service import SpotifyDeviceService
from common.config import Config

logger = logging.getLogger(__name__)


class SpotifyController:
    ARTIST_CONTEXT_WAIT_ATTEMPTS = 80
    ARTIST_CONTEXT_WAIT_SECONDS = 0.25

    def __init__(self):
        config = Config.get_instance()
        self.config = config
        scope = 'user-library-read,user-follow-read,user-read-playback-state,user-modify-playback-state,playlist-read-private'

        # Use the config directory for a consistent cache location across users/services.
        cache_path = os.path.join(config.config_dir, 'cache', 'token-cache')
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        cache_handler = CacheFileHandler(cache_path=cache_path, username="spotify-cmd")

        self.spotipy_client = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=config.spotify_client_id,
                                                                        client_secret=config.spotify_client_secret,
                                                                        redirect_uri=config.spotify_redirect_uri,
                                                                        scope=scope,
                                                                        cache_handler=cache_handler,
                                                                        open_browser=True))
        self._devices = SpotifyDeviceService(self.spotipy_client, config.device_name)
        self.session = PlaybackSession()
        # Keep the daemon available while Spotify Connect has no device yet.
        # Each command retries device discovery and reports its error to the client.
        try:
            self.ensure_device_active(force_play=False, retries=1, delay=0)
        except Exception as error:
            logger.warning('Spotify device unavailable at startup: %s', error)

    @property
    def device_name(self):
        return self._devices.device_name

    @device_name.setter
    def device_name(self, value):
        self._devices.device_name = value

    @property
    def device_id(self):
        return self._devices.device_id

    @device_id.setter
    def device_id(self, value):
        self._devices.device_id = value

    def refresh_device_id(self):
        return self._devices.refresh()

    def ensure_device_active(self, force_play=False, retries=2, delay=1):
        return self._devices.ensure_active(force_play, retries, delay, sleep=time.sleep)

    def execute_command(self, socket_message):
        command_data = socket_message.payload
        command = command_data.get('command')

        try:
            # Activating a device must not resume its previous queue before a
            # requested album, playlist, or artist is sent to Spotify.
            # Seek uses the already selected device.  It can be sent repeatedly
            # from the TUI, so device discovery must not add two Spotify API
            # requests to every press of an arrow key.
            if command != 'seek':
                self.ensure_device_active(force_play=False)
            if command == 'play':
                return self.handle_play(command_data)
            elif command == 'pause':
                return operations.pause_playback(self.spotipy_client, self.device_id)
            elif command == 'stop':
                return operations.stop_playback(self.spotipy_client, self.device_id)
            elif command == 'next':
                return operations.next_track(self.spotipy_client, self.device_id)
            elif command == 'previous':
                return operations.previous_track(self.spotipy_client, self.device_id)
            elif command == 'seek':
                return operations.seek_playback(self.spotipy_client, self.device_id, command_data.get('value'))
            elif command == 'set':
                return self.handle_set(command_data)
            elif command == 'get':
                return self.handle_get(command_data)
            elif command == 'find':
                return self.handle_search(command_data)
            return {'error': f'Unsupported command: {command}'}
        except SpotifyException as e:
            print(f"Spotify error: {e}")
            return {"error": str(e)}
        except Exception as e:
            print(f"Error: {e}")
            return {"error": str(e)}

    def handle_search(self, command_data):
        type = command_data.get('type')
        search_query = command_data.get('value')

        return operations.search(self.spotipy_client, search_query, type)


    def handle_play(self, command_data):
        type = command_data.get('type')

        if type:
            value = command_data.get('value')
            if type == 'context':
                resource_uri = value['uri']
                offset = value['offset']
            elif type == 'queue_track':
                context = self._artist_queue_context_for(value)
                queue = self.session.artist_queue()
                response = operations.play_queue_track(
                    self.spotipy_client, self.device_id, value, context,
                    queue.tracks if queue and context else (),
                )
                if context and 'error' not in response:
                    self.session.clear_artist_queue(queue)
                return response
            else:
                resource_uri = get_resource_uri(self.spotipy_client, type, value)
                offset = None
            name = None
            if type not in ('uri', 'context'):
                name = value

            response = operations.start_playback(self.spotipy_client, self.device_id, resource_uri, name, offset)
            if 'error' not in response:
                if resource_uri.startswith('spotify:artist:'):
                    self._start_artist_queue(resource_uri, name)
                else:
                    self.session.clear_artist_queue()
            return response
        else:
            return operations.resume_playback(self.spotipy_client, self.device_id)

    def handle_set(self, command_data):
        setting = command_data.get('setting')
        value = command_data.get('value')
        if setting == 'shuffle':
            return operations.set_shuffle(self.spotipy_client, self.device_id, value)
        elif setting == 'volume':
            return operations.set_volume(self.spotipy_client, self.device_id, value)
        return {'error': f'Unsupported setting: {setting}'}

    def handle_get(self, command_data):
        type = command_data.get('type')
        if type == 'albums':
            return operations.get_library_albums(self.spotipy_client)
        elif type == 'artist_albums':
            return operations.get_artist_albums(self.spotipy_client, command_data.get('value'))
        elif type == 'artists':
            return operations.get_library_artists(self.spotipy_client)
        elif type == 'playlists':
            return operations.get_library_playlists(self.spotipy_client)
        elif type == 'queue':
            return self._get_queue()
        elif type == 'tracks':
            return operations.get_context_tracks(self.spotipy_client, command_data.get('value'))
        return {'error': f'Unsupported resource: {type}'}

    def _start_artist_queue(self, uri, name):
        return self.session.begin_artist_queue(uri, name)

    def _artist_queue_context_for(self, track_uri):
        artist_queue = self.session.artist_queue()
        track_id = track_uri.rsplit(':', 1)[-1]
        if artist_queue and not artist_queue.pending and track_id in {track['spotify_id'] for track in artist_queue.tracks}:
            return artist_queue.uri
        return None

    def _get_queue(self):
        artist_queue = self.session.artist_queue()
        if artist_queue and artist_queue.pending:
            return self._wait_for_artist_queue(artist_queue)
        response = operations.get_queue(self.spotipy_client)
        playback = self._current_playback()
        context_uri = (playback.get('context') or {}).get('uri')
        current_id = (playback.get('item') or {}).get('id')
        if not artist_queue:
            return response
        if context_uri == artist_queue.uri:
            # Spotify rotates and mutates the artist queue as playback moves.
            # The session owns the initial ordered snapshot so the TUI list does
            # not jump or reorder beneath the selection.
            return {
                'tracks': list(artist_queue.tracks),
                'playing_id': current_id or response.get('playing_id'),
                'artist_context_uri': artist_queue.uri,
                'artist_context_name': artist_queue.name,
            }
        track_ids = {track['spotify_id'] for track in artist_queue.tracks}
        if current_id in track_ids:
            return {
                'tracks': list(artist_queue.tracks), 'playing_id': current_id,
                'artist_context_uri': artist_queue.uri, 'artist_context_name': artist_queue.name,
            }
        self.session.clear_artist_queue(artist_queue)
        return response

    def _wait_for_artist_queue(self, artist_queue):
        for _ in range(self.ARTIST_CONTEXT_WAIT_ATTEMPTS):
            playback = self._current_playback()
            if self._is_artist_playing(playback, artist_queue.uri):
                response = operations.get_queue(self.spotipy_client)
                if response['tracks']:
                    completed_queue = self.session.complete_artist_queue(artist_queue, response['tracks'])
                    if completed_queue:
                        return {**response, 'artist_context_uri': completed_queue.uri, 'artist_context_name': completed_queue.name}
                    return response
            time.sleep(self.ARTIST_CONTEXT_WAIT_SECONDS)
        self.session.clear_artist_queue(artist_queue)
        return {'error': 'Spotify did not start the selected artist.'}

    def _current_playback(self):
        return getattr(self.spotipy_client, 'current_playback', lambda: None)() or {}

    @staticmethod
    def _is_artist_playing(playback, uri):
        if (playback.get('context') or {}).get('uri') == uri:
            return True
        artist_id = uri.rsplit(':', 1)[-1]
        return artist_id in {artist.get('id') for artist in (playback.get('item') or {}).get('artists', [])}

    def get_playback_state(self):
        """Return the Spotify state needed by MPRIS without changing playback."""
        playback = self.spotipy_client.current_playback() or {}
        item = playback.get('item') or {}
        state = {
            'is_playing': playback.get('is_playing', False),
            'progress_ms': playback.get('progress_ms', 0) or 0,
            'shuffle_state': playback.get('shuffle_state', False),
            'volume_percent': (playback.get('device') or {}).get('volume_percent', 0) or 0,
            'item': item,
            'context': playback.get('context') or {},
        }
        artist_queue = self.session.artist_queue()
        track_ids = {track['spotify_id'] for track in artist_queue.tracks} if artist_queue else set()
        if artist_queue and not artist_queue.pending and item.get('id') in track_ids:
            state['display_context'] = {'uri': artist_queue.uri, 'name': artist_queue.name}
        return state
