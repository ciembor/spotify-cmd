from dataclasses import dataclass, field
from enum import IntEnum


class View(IntEnum):
    ALBUMS = 0
    PLAYLISTS = 1
    NOW_PLAYING = 2


VIEW_RESOURCES = {View.ALBUMS: 'albums', View.PLAYLISTS: 'playlists', View.NOW_PLAYING: 'queue'}
VIEW_TITLES = {View.ALBUMS: 'Albums', View.PLAYLISTS: 'Playlists', View.NOW_PLAYING: 'Now playing'}


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
    is_playing: bool = False
    shuffle_enabled: bool = False
    message: str = ''
    loading: bool = False
    track_context: TrackContext | None = None
    expected_playing_id: str | None = None

    @property
    def resource(self):
        return 'tracks' if self.view is View.NOW_PLAYING and self.track_context else VIEW_RESOURCES[self.view]

    @property
    def resource_value(self):
        return self.track_context.uri if self.resource == 'tracks' else None

    @property
    def title(self):
        return self.track_context.name if self.view is View.NOW_PLAYING and self.track_context else VIEW_TITLES[self.view]

    @property
    def selected_item(self):
        return self.items[self.selected] if self.items else None

    def select_view(self, view):
        if view == self.view == View.NOW_PLAYING:
            return False
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
        self.message = response.get('error', '')
        self.items = response.get(resource if resource != 'queue' else 'tracks', [])
        self.playing_id = response.get('playing_id', self.playing_id)
        if resource == 'tracks' and self.playing_id:
            self.selected = next((i for i, item in enumerate(self.items) if item['spotify_id'] == self.playing_id), self.selected)
        elif selected_id:
            self.selected = next((i for i, item in enumerate(self.items) if item['spotify_id'] == selected_id), self.selected)
        self.selected = min(self.selected, max(len(self.items) - 1, 0))
        self.keep_selected_visible()
