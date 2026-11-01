from dataclasses import dataclass, field
from enum import IntEnum


class View(IntEnum):
    ALBUMS = 0
    PLAYLISTS = 1
    ARTISTS = 2
    NOW_PLAYING = 3


VIEW_RESOURCES = {View.ALBUMS: 'albums', View.PLAYLISTS: 'playlists', View.ARTISTS: 'artists', View.NOW_PLAYING: 'queue'}
VIEW_TITLES = {View.ALBUMS: 'Albums', View.PLAYLISTS: 'Playlists', View.ARTISTS: 'Artists', View.NOW_PLAYING: 'Now playing'}


@dataclass(frozen=True)
class TrackContext:
    uri: str
    name: str


@dataclass
class TuiState:
    view: View = View.ALBUMS
    items: list[dict] = field(default_factory=list)
    selected: int = 0
    first_visible: int = 0
    visible_rows: int = 1
    playing_id: str | None = None
    playback_id: str | None = None
    linked_playback_id: str | None = None
    playing_track_number: int | None = None
    playing_disc_number: int | None = None
    is_playing: bool = False
    progress_ms: int = 0
    duration_ms: int = 0
    shuffle_enabled: bool = False
    message: str = ''
    message_is_error: bool = False
    loading: bool = False
    track_context: TrackContext | None = None
    queue_context: TrackContext | None = None
    artist_context: TrackContext | None = None
    expected_playing_id: str | None = None
    latest_state_revision: int = 0

    def set_response_message(self, response):
        self.message_is_error = bool(response.get('error'))
        self.message = response.get('error') or response.get('notification', '')

    def accept_state_revision(self, revision):
        if revision is not None:
            self.latest_state_revision = max(self.latest_state_revision, revision)

    def accepts_event_revision(self, revision):
        if revision is None:
            return True
        if revision <= self.latest_state_revision:
            return False
        self.latest_state_revision = revision
        return True

    @property
    def resource(self):
        if self.view is View.ARTISTS and self.artist_context:
            return 'artist_albums'
        return 'tracks' if self.view is View.NOW_PLAYING and self.track_context else VIEW_RESOURCES[self.view]

    @property
    def resource_value(self):
        if self.resource == 'artist_albums':
            return self.artist_context.uri
        return self.track_context.uri if self.resource == 'tracks' else None

    @property
    def title(self):
        if self.view is View.NOW_PLAYING:
            context = self.track_context or self.queue_context
            return context.name if context else VIEW_TITLES[self.view]
        return VIEW_TITLES[self.view]

    @property
    def selected_item(self):
        return self.items[self.selected] if self.items else None

    def update_playing_item(self, item):
        self.playback_id = item.get('id')
        self.linked_playback_id = (item.get('linked_from') or {}).get('id')
        self.playing_track_number = item.get('track_number')
        self.playing_disc_number = item.get('disc_number')
        self.playing_id = self._display_playing_id(self.playback_id)

    def matches_item(self, item, spotify_id):
        if item.get('id') == spotify_id:
            return True
        return (item.get('linked_from') or {}).get('id') == spotify_id

    def _display_playing_id(self, playback_id):
        direct_match = next((item for item in self.items if item.get('spotify_id') == playback_id), None)
        if direct_match:
            return direct_match['spotify_id']
        linked_match = next((item for item in self.items
                             if item.get('spotify_id') == self.linked_playback_id), None)
        return linked_match['spotify_id'] if linked_match else playback_id

    def select_view(self, view):
        if view == self.view == View.NOW_PLAYING:
            return False
        if View(view) is View.ARTISTS:
            self.artist_context = None
        self.view, self.selected, self.first_visible = View(view), 0, 0
        return True

    def move(self, amount):
        if self.items:
            self.selected = max(0, min(self.selected + amount, len(self.items) - 1))
            self.keep_selected_visible()

    def show_playing_context(self, uri, name, resource_type):
        self.view = View.NOW_PLAYING
        self.selected = 0
        self.first_visible = 0
        self.track_context = TrackContext(uri, name) if resource_type in ('album', 'playlist') else None
        self.queue_context = TrackContext(uri, name) if resource_type == 'artist' else None

    def update_playback_context(self, context):
        uri = (context or {}).get('uri') or ''
        if not uri:
            return False  # Spotify may omit context after selecting a track from an artist queue.
        if uri.startswith('spotify:artist:'):
            if self.queue_context and self.queue_context.uri == uri:
                return False
            self.track_context = None
            self.queue_context = TrackContext(uri, 'Now playing')
            return True
        supported = uri.startswith(('spotify:album:', 'spotify:playlist:'))
        if not supported:
            changed = self.track_context is not None or self.queue_context is not None
            self.track_context = None
            self.queue_context = None
            return changed
        if self.track_context and self.track_context.uri == uri:
            return False
        self.queue_context = None
        self.track_context = TrackContext(uri, 'Now playing')
        return True

    def set_queue_context(self, uri, name):
        self.track_context = None
        self.queue_context = TrackContext(uri, name)

    def resize(self, height):
        self.visible_rows = max(height - 2, 1)
        self.keep_selected_visible()

    def keep_selected_visible(self):
        max_first = max(len(self.items) - self.visible_rows, 0)
        self.first_visible = min(self.first_visible, max_first)
        if self.selected < self.first_visible:
            self.first_visible = self.selected
        elif self.selected >= self.first_visible + self.visible_rows:
            self.first_visible = self.selected - self.visible_rows + 1
        self.first_visible = min(self.first_visible, max_first)

    def apply_response(self, resource, response, selected_id):
        self.loading = False
        self.set_response_message({'error': response.get('error', '')})
        self.items = response.get(resource if resource != 'queue' else 'tracks', [])
        self.playing_track_number = response.get('playing_track_number', self.playing_track_number)
        self.playing_disc_number = response.get('playing_disc_number', self.playing_disc_number)
        self.playback_id = response.get('playing_id', self.playback_id)
        self.playing_id = self._display_playing_id(self.playback_id)
        if resource == 'tracks' and self.track_context and response.get('context_name'):
            self.track_context = TrackContext(self.track_context.uri, response['context_name'])
        if resource == 'tracks' and self.playing_id:
            self.selected = next((i for i, item in enumerate(self.items) if item['spotify_id'] == self.playing_id), self.selected)
        elif selected_id:
            self.selected = next((i for i, item in enumerate(self.items) if item['spotify_id'] == selected_id), self.selected)
        self.selected = min(self.selected, max(len(self.items) - 1, 0))
        self.keep_selected_visible()
