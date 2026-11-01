import pytest

from spotify_cmd_daemon.operations.playlist_tracks import playlist_tracks
from spotify_cmd_daemon.operations.start_playback import start_playback
from spotify_cmd_ui_client.controller import TuiController
from spotify_cmd_ui_client.state import TrackContext, View


class Playlist:
    def __init__(self):
        self.calls = []
        self.pages = [
            [{'track': {'id': 'skipping', 'is_playable': False}}, {'track': None}],
            [{'track': {'id': 'local', 'is_local': True}},
             {'track': {'id': 'replacement', 'is_playable': True}}],
        ]

    def playlist(self, *_):
        return {}

    def playlist_items(self, uri, limit, offset, market):
        assert market == 'from_token'
        self.calls.append(offset)
        return {'items': self.pages[offset // 2], 'next': bool(self.pages[offset // 2]) and offset == 0}

    def start_playback(self, **kwargs):
        self.play = kwargs


def test_availability_preserves_positions_across_pages():
    api = Playlist()
    tracks = list(playlist_tracks(api, 'playlist'))
    assert [t['context_position'] for t in tracks] == [0, 1, 2, 3]
    assert [t['is_playable'] for t in tracks] == [False, False, False, True]
    assert tracks[0]['id'] == 'skipping'
    assert api.calls == [0, 2]


def test_start_uses_first_playable_original_position_and_resets_time():
    api = Playlist()
    assert 'notification' in start_playback(api, 'device', 'spotify:playlist:p')
    assert api.play == {'context_uri': 'spotify:playlist:p', 'device_id': 'device',
                        'offset': {'uri': 'spotify:track:replacement'}, 'position_ms': 0}


def test_start_uses_playlist_position_only_for_an_explicit_track_selection():
    api = Playlist()

    start_playback(api, 'device', 'spotify:playlist:p')
    assert api.play['offset'] == {'uri': 'spotify:track:replacement'}

    start_playback(api, 'device', 'spotify:playlist:p', offset=3)
    assert api.play['offset'] == {'position': 3}


def test_unavailable_selection_and_empty_playlist_do_not_send_play():
    api = Playlist()
    assert 'error' in start_playback(api, 'device', 'spotify:playlist:p', offset=0)
    api.pages = [[], []]
    assert 'error' in start_playback(api, 'device', 'spotify:playlist:p')
    assert not hasattr(api, 'play')


def test_tui_uses_original_position_after_unavailable_rows_are_removed():
    class Gateway:
        def play(self, kind, value):
            self.value = value
            return {'notification': 'started'}
    gateway = Gateway()
    ui = TuiController(gateway)
    try:
        ui.state.view = View.NOW_PLAYING
        ui.state.track_context = TrackContext('spotify:playlist:p', 'P')
        ui.state.items = [{'spotify_id': 'replacement', 'context_position': 3}]
        ui.play_selected()
        assert gateway.value == {'uri': 'spotify:playlist:p', 'offset': 3}
    finally:
        ui.close()


def test_unavailable_row_is_visible_and_cannot_send_play():
    from spotify_cmd_ui_client.view import CursesView
    class Gateway:
        def play(self, *_):
            raise AssertionError('Unavailable tracks must not send play')
    ui = TuiController(Gateway())
    try:
        row = {'spotify_id': 'skipping', 'name': 'Skipping', 'artists': 'Yosi Horikawa',
               'is_playable': False}
        ui.state.items = [row]
        ui.state.view = View.NOW_PLAYING
        ui.play_selected()
        assert 'No playable tracks remaining' in ui.state.message
        assert CursesView._item_label(row, View.NOW_PLAYING) == 'Skipping [unavailable]  ●  Yosi Horikawa'
        assert ui.state.playing_id is None
    finally:
        ui.close()


@pytest.mark.parametrize('context', ['spotify:playlist:p', 'spotify:album:a', None])
@pytest.mark.parametrize('playable', [True, None])
def test_unavailable_selection_advances_to_next_playable_and_scrolls(context, playable):
    class Gateway:
        def __init__(self):
            self.calls = []

        def play(self, kind, value):
            self.calls.append((kind, value))
            return {'notification': 'started'}

    gateway = Gateway()
    ui = TuiController(gateway)
    try:
        ui.state.view = View.NOW_PLAYING
        ui.state.track_context = TrackContext(context, 'Context') if context else None
        rows = [{'spotify_id': 'unavailable', 'is_playable': False},
                {'spotify_id': 'also-unavailable', 'is_playable': False},
                {'spotify_id': 'next', 'context_position': 7}]
        if playable is not None:
            rows[-1]['is_playable'] = playable
        ui.state.items = rows
        ui.state.visible_rows = 1
        ui.play_selected()
        expected = ('context', {'uri': context, 'offset': 7}) if context else ('queue_track', 'spotify:track:next')
        assert gateway.calls == [expected]
        assert ui.state.selected == ui.state.first_visible == 2
        assert ui.state.playing_id == 'next'
        assert ui.state.items == rows
        assert not ui.state.message_is_error
    finally:
        ui.close()


def test_unavailable_last_track_does_not_wrap_or_change_current_playback():
    class Gateway:
        def play(self, *args):
            raise AssertionError('No next playable track')

    ui = TuiController(Gateway())
    try:
        ui.state.view = View.NOW_PLAYING
        ui.state.items = [{'spotify_id': 'earlier'}, {'spotify_id': 'last', 'is_playable': False}]
        ui.state.selected = 1
        ui.state.playing_id = 'earlier'
        ui.play_selected()
        assert ui.state.selected == 1
        assert ui.state.playing_id == 'earlier'
        assert 'No playable tracks remaining' in ui.state.message
    finally:
        ui.close()
