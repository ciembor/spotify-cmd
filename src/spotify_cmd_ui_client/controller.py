from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Empty, Queue
import threading

from .gateway import RequestCancellation, SpotifyGateway
from .state import TuiState, View


@dataclass(frozen=True)
class LoadResult:
    token: int
    resource: str
    value: str | None
    selected_id: str | None
    response: dict


class TuiController:
    """Coordinates user input, daemon events, and renderable UI state."""

    LOAD_DEBOUNCE_SECONDS = 0.15

    def __init__(self, gateway=None):
        self.gateway = gateway or SpotifyGateway()
        self.state = TuiState()
        self._events, self._results = Queue(), Queue()
        self._loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix='spotify-cmd-load')
        self._load_token = 0
        self._active_cancellation = None
        self._active_future = None
        self._subscription_stop = threading.Event()

    def start(self):
        self.start_load()
        threading.Thread(target=self.gateway.subscribe, args=(self._events.put, self._subscription_stop), daemon=True).start()

    def close(self):
        self._subscription_stop.set()
        self._cancel_active_load()
        self._loader.shutdown(wait=False, cancel_futures=True)

    def resize(self, height):
        self.state.resize(height)

    def tick(self):
        self._process_events()
        self._process_results()

    def _process_events(self):
        while True:
            try:
                event = self._events.get_nowait()
            except Empty:
                return
            if event.get('event') == 'connection_error':
                self.state.message = event['error']
                continue
            if event.get('event') == 'connection_restored':
                self.start_load()
                continue
            if event.get('event') != 'state_changed':
                continue
            playback_state = event.get('state', {})
            self.state.playing_id = playback_state.get('item', {}).get('id')
            self.state.is_playing = playback_state.get('is_playing', self.state.is_playing)
            self.state.shuffle_enabled = playback_state.get('shuffle_state', self.state.shuffle_enabled)
            if self.state.playing_id == self.state.expected_playing_id:
                self.state.expected_playing_id = None
            elif self.state.view is View.NOW_PLAYING and not self.state.track_context and not self.state.loading:
                self.start_load()

    def _process_results(self):
        while True:
            try:
                result = self._results.get_nowait()
            except Empty:
                return
            if result.token == self._load_token and (result.resource, result.value) == (self.state.resource, self.state.resource_value):
                self.state.apply_response(result.resource, result.response, result.selected_id)

    def start_load(self):
        self._cancel_active_load()
        self._load_token += 1
        token, resource, value = self._load_token, self.state.resource, self.state.resource_value
        selected = self.state.selected_item
        self.state.loading = True
        cancellation = RequestCancellation()
        self._active_cancellation = cancellation
        self._active_future = self._loader.submit(
            self._load, token, resource, value, selected.get('spotify_id') if selected else None, cancellation,
        )

    def _cancel_active_load(self):
        if self._active_cancellation:
            self._active_cancellation.cancel()
        if self._active_future:
            self._active_future.cancel()

    def _load(self, token, resource, value, selected_id, cancellation):
        # Coalesce rapid view switches before they become expensive Spotify API
        # requests on the daemon.
        if cancellation.wait(self.LOAD_DEBOUNCE_SECONDS):
            return
        try:
            response = self.gateway.load(resource, value, cancellation)
        except Exception as error:
            response = {'error': f'Could not load {resource}: {error}'}
        if not cancellation.cancelled:
            self._results.put(LoadResult(token, resource, value, selected_id, response))

    def select_view(self, view):
        if self.state.select_view(view):
            self.start_load()

    def move(self, amount):
        if not self.state.loading:
            self.state.move(amount)

    def toggle_playback(self):
        command = 'pause' if self.state.is_playing else 'play'
        if self._apply_command(self.gateway.command(command)):
            self.state.is_playing = not self.state.is_playing

    def stop(self):
        self._apply_command(self.gateway.command('stop'))

    def toggle_shuffle(self):
        enabled = not self.state.shuffle_enabled
        if self._apply_command(self.gateway.command('set', 'shuffle', 'on' if enabled else 'off')):
            self.state.shuffle_enabled = enabled

    def play_selected(self):
        if self.state.loading or not self.state.selected_item:
            return
        item = self.state.selected_item
        if self.state.view is View.NOW_PLAYING and self.state.track_context:
            self._apply_play(self.gateway.play('context', {'uri': self.state.track_context.uri, 'offset': self.state.selected}), item['spotify_id'])
        elif self.state.view is View.NOW_PLAYING:
            self._apply_play(self.gateway.play('queue_track', f"spotify:track:{item['spotify_id']}"), item['spotify_id'], expect_event=True)
        else:
            self._play_resource(item)

    def _play_resource(self, item):
        resource_type = item['type'].rstrip('s')
        uri = f"spotify:{resource_type}:{item['spotify_id']}"
        response = self.gateway.play('uri', uri)
        self.state.message = response.get('error') or response.get('notification', '')
        if 'error' not in response:
            self.state.show_playing_context(uri, item['name'], resource_type)
            self.start_load()

    def _apply_play(self, response, playing_id, expect_event=False):
        self.state.message = response.get('error') or response.get('notification', '')
        if 'error' not in response:
            self.state.playing_id = playing_id
            self.state.expected_playing_id = playing_id if expect_event else None

    def _apply_command(self, response):
        self.state.message = response.get('error') or response.get('notification', '')
        return 'error' not in response
