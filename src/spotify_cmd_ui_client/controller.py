from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Empty, Queue
import threading
import time

from .gateway import CommandResult, RequestCancellation, SpotifyGateway
from .playback_transition import PlaybackTransition
from .state import TrackContext, TuiState, View


@dataclass(frozen=True)
class LoadResult:
    token: int
    resource: str
    value: str | None
    selected_id: str | None
    response: dict
    playback_generation: int = 0


@dataclass(frozen=True)
class SeekResult:
    token: int
    target_ms: int
    response: dict


class TuiController:
    """Coordinates user input, daemon events, and renderable UI state."""

    LOAD_DEBOUNCE_SECONDS = 0.15
    SEEK_MILLISECONDS = 10_000
    SEEK_DEBOUNCE_SECONDS = 0.08
    CONTEXT_TRANSITION_GRACE_SECONDS = 5
    PLAYBACK_TRANSITION_GRACE_SECONDS = 5

    def __init__(self, gateway=None):
        self.gateway = gateway or SpotifyGateway()
        self.state = TuiState()
        self._events, self._results = Queue(), Queue()
        self._loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix='spotify-cmd-load')
        self._seeker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='spotify-cmd-seek')
        self._load_token = 0
        self._active_cancellation = None
        self._active_future = None
        self._seek_results = Queue()
        self._seek_token = 0
        self._pending_seek_target = None
        self._seek_due_at = None
        self._seek_in_flight = False
        self._transition = PlaybackTransition(
            self.CONTEXT_TRANSITION_GRACE_SECONDS, self.PLAYBACK_TRANSITION_GRACE_SECONDS,
        )
        self._artist_list = None
        self._context_load_uri = None
        self._playback_generation = 0
        self._subscription_stop = threading.Event()

    def start(self):
        self.start_load()
        threading.Thread(target=self.gateway.subscribe, args=(self._events.put, self._subscription_stop), daemon=True).start()

    def close(self):
        self._subscription_stop.set()
        self._cancel_active_load()
        self._loader.shutdown(wait=False, cancel_futures=True)
        self._seeker.shutdown(wait=False, cancel_futures=True)

    def resize(self, height):
        self.state.resize(height)

    def tick(self):
        self._process_events()
        self._process_results()
        self._process_seek_results()
        self._dispatch_pending_seek()

    def _process_events(self):
        while True:
            try:
                event = self._events.get_nowait()
            except Empty:
                return
            if event.get('event') == 'connection_error':
                self.state.set_response_message({'error': event['error']})
                continue
            if event.get('event') == 'connection_restored':
                self.state.latest_state_revision = 0
                self._playback_generation += 1
                self.start_load()
                continue
            if event.get('event') != 'state_changed':
                continue
            if not self.state.accepts_event_revision(event.get('state_revision')):
                continue
            playback_state = event.get('state', {})
            if self._transition.stale_item(self.state, playback_state.get('item', {})):
                continue
            playback_context = playback_state.get('display_context', playback_state.get('context'))
            if self._transition.stale_context(playback_context):
                continue
            self._playback_generation += 1
            item_id = playback_state.get('item', {}).get('id')
            playing_changed = item_id is not None and item_id != self.state.playback_id
            # The desktop client briefly reports an empty item while it changes
            # an artist queue track.  Keep the known marker in its queue until
            # Spotify supplies the replacement item; a real paused state still
            # includes its current item and updates it normally.
            if not self._seeking:
                self.state.progress_ms = playback_state.get('progress_ms', self.state.progress_ms) or 0
            self.state.duration_ms = playback_state.get('item', {}).get('duration_ms', self.state.duration_ms) or 0
            self.state.is_playing = playback_state.get('is_playing', self.state.is_playing)
            self.state.shuffle_enabled = playback_state.get('shuffle_state', self.state.shuffle_enabled)
            context_changed = False
            context_confirmed = self._transition.context_confirmed
            if playback_context is not None:
                context_changed = self.state.update_playback_context(playback_context)
            if item_id or not (self.state.track_context or self.state.queue_context):
                self.state.update_playing_item(playback_state.get('item', {}))
            if context_confirmed and playback_context.get('uri') == self._context_load_uri:
                # _play_resource already requested these tracks.  The playback
                # event confirms that request instead of starting a duplicate.
                self._context_load_uri = None
                context_confirmed = False
            if self.state.view is View.NOW_PLAYING and (context_changed or context_confirmed):
                self.start_load()
            elif (playing_changed and self.state.view is View.NOW_PLAYING
                  and not self.state.track_context and not self.state.queue_context and not self.state.loading):
                self.start_load()

    def _process_results(self):
        while True:
            try:
                result = self._results.get_nowait()
            except Empty:
                return
            if result.token == self._load_token and (result.resource, result.value) == (self.state.resource, self.state.resource_value):
                if result.playback_generation != self._playback_generation:
                    response = dict(result.response)
                    for key in ('playing_id', 'playing_track_number', 'playing_disc_number'):
                        response.pop(key, None)
                    result = LoadResult(result.token, result.resource, result.value, result.selected_id, response,
                                        result.playback_generation)
                if result.resource == 'queue' and result.response.get('artist_context_uri'):
                    self.state.set_queue_context(
                        result.response['artist_context_uri'], result.response['artist_context_name'],
                    )
                if result.resource == 'queue' and result.response.get('context_uri'):
                    self.state.update_playback_context({'uri': result.response['context_uri']})
                    if context_tracks := result.response.get('context_tracks'):
                        self.state.apply_response('tracks', {
                            'tracks': context_tracks,
                            'playing_id': result.response.get('playing_id', self.state.playback_id),
                            'context_name': result.response.get('context_name'),
                        }, result.selected_id)
                    else:
                        self.start_load()
                    continue
                self.state.apply_response(result.resource, result.response, result.selected_id)

    def _process_seek_results(self):
        while True:
            try:
                result = self._seek_results.get_nowait()
            except Empty:
                return
            self._seek_in_flight = False
            response = self._unwrap_response(result.response)
            self.state.set_response_message(response)
            if 'error' in response:
                if self._pending_seek_target == result.target_ms:
                    self._pending_seek_target = None
                continue
            if self._pending_seek_target == result.target_ms:
                self._pending_seek_target = None
                self.state.progress_ms = response.get('progress_ms', result.target_ms)

    def _dispatch_pending_seek(self):
        if self._pending_seek_target is None or self._seek_in_flight or time.monotonic() < self._seek_due_at:
            return
        target_ms = self._pending_seek_target
        self._seek_token += 1
        self._seek_in_flight = True
        self._seeker.submit(self._run_seek, self._seek_token, target_ms)

    def _run_seek(self, token, target_ms):
        try:
            response = self._command('seek', value=target_ms)
        except Exception as error:
            response = {'error': f'Could not seek: {error}'}
        self._seek_results.put(SeekResult(token, target_ms, response))

    def _expect_context(self, uri):
        self._transition.expect_context(uri)

    def _expect_playing_item(self, spotify_id):
        self._transition.expect_item(self.state, spotify_id)

    @property
    def _expected_context_uri(self):
        return self._transition.expected_context_uri

    @property
    def _expected_context_deadline(self):
        return self._transition.expected_context_deadline

    @_expected_context_deadline.setter
    def _expected_context_deadline(self, value):
        self._transition.expected_context_deadline = value

    @property
    def _expected_playing_deadline(self):
        return self._transition.expected_item_deadline

    @_expected_playing_deadline.setter
    def _expected_playing_deadline(self, value):
        self._transition.expected_item_deadline = value

    def start_load(self):
        self._cancel_active_load()
        self._load_token += 1
        token, resource, value = self._load_token, self.state.resource, self.state.resource_value
        selected = self.state.selected_item
        self.state.loading = True
        cancellation = RequestCancellation()
        self._active_cancellation = cancellation
        self._active_future = self._loader.submit(
            self._load, token, resource, value, selected.get('spotify_id') if selected else None, cancellation, self._playback_generation,
        )

    def _cancel_active_load(self):
        if self._active_cancellation:
            self._active_cancellation.cancel()
        if self._active_future:
            self._active_future.cancel()

    def _load(self, token, resource, value, selected_id, cancellation, playback_generation=0):
        # Coalesce rapid view switches before they become expensive Spotify API
        # requests on the daemon.
        if cancellation.wait(self.LOAD_DEBOUNCE_SECONDS):
            return
        try:
            response = self.gateway.load(resource, value, cancellation)
        except Exception as error:
            response = {'error': f'Could not load {resource}: {error}'}
        if not cancellation.cancelled:
            self._results.put(LoadResult(token, resource, value, selected_id, response, playback_generation))

    def select_view(self, view):
        if self.state.select_view(view):
            self.start_load()

    def move(self, amount):
        if not self.state.loading:
            self.state.move(amount)

    def toggle_playback(self):
        command = 'pause' if self.state.is_playing else 'play'
        if self._apply_command(self._command(command)):
            self.state.is_playing = not self.state.is_playing

    def stop(self):
        self._apply_command(self._command('stop'))

    def seek(self, direction):
        if not self.state.duration_ms:
            return
        target = self.state.progress_ms + direction * self.SEEK_MILLISECONDS
        self._pending_seek_target = min(max(target, 0), self.state.duration_ms)
        self._seek_due_at = time.monotonic() + self.SEEK_DEBOUNCE_SECONDS
        self.state.progress_ms = self._pending_seek_target

    @property
    def _seeking(self):
        return self._seek_in_flight or self._pending_seek_target is not None

    def toggle_shuffle(self):
        enabled = not self.state.shuffle_enabled
        if self._apply_command(self._command('set', 'shuffle', 'on' if enabled else 'off')):
            self.state.shuffle_enabled = enabled

    def play_selected(self):
        if self.state.loading or not self.state.selected_item:
            return
        if self.state.view is View.ARTISTS and self.state.artist_context is None:
            self._open_artist_albums(self.state.selected_item)
            return
        item = self._select_next_playable_item()
        if item is None:
            self.state.set_response_message({'error': 'No playable tracks remaining in this list.'})
            return
        if self.state.view is View.NOW_PLAYING and self.state.track_context:
            self._apply_play(self._play('context', {'uri': self.state.track_context.uri, 'offset': item.get('context_position', self.state.selected)}), item['spotify_id'])
        elif self.state.view is View.NOW_PLAYING:
            self._apply_play(self._play('queue_track', f"spotify:track:{item['spotify_id']}"), item['spotify_id'])
        else:
            self._play_resource(item)

    def _open_artist_albums(self, artist):
        self._artist_list = (list(self.state.items), self.state.selected, self.state.first_visible)
        self.state.artist_context = TrackContext(f"spotify:artist:{artist['spotify_id']}", artist['name'])
        self.state.items = []
        self.state.selected = self.state.first_visible = 0
        self.start_load()

    def navigate_back(self):
        if self.state.view is not View.ARTISTS or self.state.artist_context is None:
            return False
        self._cancel_active_load()
        self._load_token += 1
        self.state.artist_context = None
        self.state.items, self.state.selected, self.state.first_visible = self._artist_list
        self.state.keep_selected_visible()
        self.state.loading = False
        self.state.set_response_message({})
        return True

    def _select_next_playable_item(self):
        for index in range(self.state.selected, len(self.state.items)):
            item = self.state.items[index]
            if item.get('is_playable') is not False:
                self.state.selected = index
                self.state.keep_selected_visible()
                return item
        return None

    def _play_resource(self, item):
        resource_type = item['type'].rstrip('s')
        uri = f"spotify:{resource_type}:{item['spotify_id']}"
        response = self._unwrap_response(self._play('uri', uri))
        self.state.set_response_message(response)
        if 'error' not in response:
            self._playback_generation += 1
            self.state.show_playing_context(uri, item['name'], resource_type)
            self._expect_context(uri)
            self._context_load_uri = uri
            self.start_load()

    def _apply_play(self, response, playing_id):
        response = self._unwrap_response(response)
        self.state.set_response_message(response)
        if 'error' not in response:
            self._playback_generation += 1
            self.state.playing_id = playing_id
            self.state.playback_id = playing_id
            self._expect_playing_item(playing_id)

    def _apply_command(self, response):
        response = self._unwrap_response(response)
        self.state.set_response_message(response)
        return 'error' not in response

    def _play(self, resource_type, value):
        play = getattr(self.gateway, 'play_with_state_revision', None) or self.gateway.play
        return play(resource_type, value)

    def _command(self, command, setting=None, value=None):
        execute = getattr(self.gateway, 'command_with_state_revision', None) or self.gateway.command
        return execute(command, setting, value)

    def _unwrap_response(self, response):
        if isinstance(response, CommandResult):
            self.state.accept_state_revision(response.state_revision)
            return response.payload
        return response
