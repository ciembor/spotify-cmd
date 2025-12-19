import os
import sys
import time
current_dir = os.path.dirname(os.path.abspath(__file__))
base_path = os.path.join(current_dir, "..", 'common')
sys.path.insert(0, base_path)

import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from spotipy.exceptions import SpotifyException
from . import operations
from .operations.helpers import get_resource_uri
from config import Config
from socket_message import SocketMessage

class SpotifyController:
    def __init__(self):
        config = Config.get_instance()
        scope = 'user-library-read,user-read-playback-state,user-modify-playback-state,playlist-read-private'

        # Force a stable cache path so auth does not depend on cwd or env.
        cache_path = os.path.expanduser('~/.config/spotify-cmd/cache/token-cache')
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        cache_handler = CacheFileHandler(cache_path=cache_path, username="spotify-cmd")

        self.spotipy_client = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=config.spotify_client_id,
                                                                        client_secret=config.spotify_client_secret,
                                                                        redirect_uri=config.spotify_redirect_uri,
                                                                        scope=scope,
                                                                        cache_handler=cache_handler,
                                                                        open_browser=True))

        self.device_name = config.device_name
        self.device_id = None
        # Refresh and activate target device on startup (with retries for boot scenarios).
        self.ensure_device_active(force_play=False, retries=5, delay=2)

    def refresh_device_id(self):
        devices = self.spotipy_client.devices()
        device = next((d for d in devices.get('devices', []) if d.get('name') == self.device_name), None)
        if not device:
            raise Exception(f"Device '{self.device_name}' not found.")
        self.device_id = device['id']
        return device

    def ensure_device_active(self, force_play=False, retries=2, delay=1):
        last_err = None
        for _ in range(retries):
            try:
                device = self.refresh_device_id()
                if not device.get('is_active'):
                    # Make target device the active one.
                    self.spotipy_client.transfer_playback(device_id=self.device_id, force_play=force_play)
                return device
            except Exception as e:
                last_err = e
                time.sleep(delay)
        # If we are here, retries exhausted.
        if last_err:
            raise last_err
        raise Exception(f"Device '{self.device_name}' could not be activated.")

    def execute_command(self, socket_message):
        print(socket_message.payload)
        command_data = socket_message.payload
        command = command_data.get('command')

        try:
            # Make sure target device is active before handling commands.
            force_play = command in ('play',)
            self.ensure_device_active(force_play=force_play)
            if command == 'play':
                self.handle_play(command_data)
            elif command == 'pause':
                self.response = operations.pause_playback(self.spotipy_client, self.device_id)
            elif command == 'next':
                self.response = operations.next_track(self.spotipy_client, self.device_id)
            elif command == 'previous':
                self.response = operations.previous_track(self.spotipy_client, self.device_id)
            elif command == 'set':
                self.handle_set(command_data)
            elif command == 'get':
                self.handle_get(command_data)
            elif command == 'find':
                self.handle_search(command_data)
        except SpotifyException as e:
            print(f"Spotify error: {e}")
            self.response = {"error": str(e)}
        except Exception as e:
            print(f"Error: {e}")
            self.response = {"error": str(e)}

    def handle_search(self, command_data):
        type = command_data.get('type')
        search_query = command_data.get('value')

        self.response = operations.search(self.spotipy_client, search_query, type)


    def handle_play(self, command_data):
        type = command_data.get('type')

        if type:
            resource_uri = get_resource_uri(self.spotipy_client, type, command_data.get('value'))
            name = None
            if not (type == 'uri'):
                name = command_data.get('value')

            self.response = operations.start_playback(self.spotipy_client, self.device_id, resource_uri, name)
        else:
            self.response = operations.resume_playback(self.spotipy_client, self.device_id)

    def handle_set(self, command_data):
        setting = command_data.get('setting')
        value = command_data.get('value')
        if setting == 'shuffle':
            self.response = operations.set_shuffle(self.spotipy_client, self.device_id, value)
        elif setting == 'volume':
            self.response = operations.set_volume(self.spotipy_client, self.device_id, value)

    def handle_get(self, command_data):
        type = command_data.get('type')
        if type == 'albums':
            self.response = operations.get_library_albums(self.spotipy_client)
        elif type == 'playlists':
            self.response = operations.get_library_playlists(self.spotipy_client)

    def get_response(self):
        print(self.response)
        return SocketMessage("response", self.response)
