import threading

from spotify_cmd_ui_client.controller import TuiController
from spotify_cmd_ui_client.state import TrackContext, TuiState, View
from spotify_cmd_ui_client.view import CursesView


def wait_for_load(controller):
    for _ in range(100):
        controller.tick()
        if not controller.state.loading:
            return
        threading.Event().wait(0.01)
    raise AssertionError('Timed out waiting for TUI data')


def test_state_scrolls_down_at_the_bottom_and_up_after_reaching_the_top():
    state = TuiState(items=[{'spotify_id': str(index)} for index in range(20)], visible_rows=5)
    for _ in range(5):
        state.move(1)
    assert (state.selected, state.first_visible) == (5, 1)
    for _ in range(14):
        state.move(1)
    assert (state.selected, state.first_visible) == (19, 15)
    state.move(-1)
    assert (state.selected, state.first_visible) == (18, 15)
    for _ in range(3):
        state.move(-1)
    assert (state.selected, state.first_visible) == (15, 15)
    state.move(-1)
    assert (state.selected, state.first_visible) == (14, 14)


def test_album_play_opens_context_tracks_and_selects_playing_track():
    class Gateway:
        def __init__(self): self.calls = []
        def load(self, resource, value, _):
            self.calls.append(('load', resource, value))
            return {'tracks': [
                {'spotify_id': 'first', 'type': 'tracks', 'name': 'First'},
                {'spotify_id': 'current', 'type': 'tracks', 'name': 'Current'},
            ], 'playing_id': 'current'}
        def play(self, resource_type, value):
            self.calls.append(('play', resource_type, value))
            return {'notification': 'Playback started.'}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.state.items = [{'spotify_id': 'album-id', 'type': 'albums', 'name': 'Album'}]
    controller.play_selected()
    wait_for_load(controller)

    assert gateway.calls[0] == ('play', 'uri', 'spotify:album:album-id')
    assert gateway.calls[1] == ('load', 'tracks', 'spotify:album:album-id')
    assert controller.state.view is View.NOW_PLAYING
    assert controller.state.selected == 1
    controller.close()


def test_queue_track_keeps_items_and_uses_queue_track_command():
    class Gateway:
        def load(self, *_): raise AssertionError('queue must not reload')
        def play(self, resource_type, value):
            self.command = resource_type, value
            return {'notification': 'Playback started.'}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.state.view = View.NOW_PLAYING
    controller.state.items = [{'spotify_id': 'first'}, {'spotify_id': 'selected'}]
    controller.state.selected = 1
    controller.play_selected()

    assert gateway.command == ('queue_track', 'spotify:track:selected')
    assert [item['spotify_id'] for item in controller.state.items] == ['first', 'selected']
    assert controller.state.playing_id == 'selected'
    controller.close()


def test_selecting_now_playing_again_preserves_context_without_loading():
    class Gateway:
        def load(self, *_): raise AssertionError('view must not reload')

    controller = TuiController(Gateway())
    controller.state.view = View.NOW_PLAYING
    controller.state.track_context = TrackContext('spotify:album:album-id', 'Album')
    controller.select_view(View.NOW_PLAYING)
    assert controller.state.track_context.uri == 'spotify:album:album-id'
    controller.close()


def test_switching_view_cancels_the_in_flight_load():
    started = threading.Event()
    cancelled = threading.Event()

    class Gateway:
        def load(self, resource, _, cancellation):
            if resource == 'albums':
                started.set()
                while not cancellation.cancelled:
                    threading.Event().wait(0.01)
                cancelled.set()
                return None
            return {'playlists': []}

    controller = TuiController(Gateway())
    controller.start_load()
    assert started.wait(1)

    controller.select_view(View.PLAYLISTS)
    assert cancelled.wait(1)
    wait_for_load(controller)

    assert controller.state.view is View.PLAYLISTS
    assert not controller.state.loading
    controller.close()


def test_rapid_view_switching_sends_only_the_final_load_to_the_daemon():
    class Gateway:
        def __init__(self):
            self.resources = []

        def load(self, resource, _, _cancellation):
            self.resources.append(resource)
            return {'playlists': []}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.start_load()
    controller.select_view(View.PLAYLISTS)
    wait_for_load(controller)

    assert gateway.resources == ['playlists']
    controller.close()


def test_play_pause_stop_and_shuffle_use_daemon_commands():
    class Gateway:
        def __init__(self): self.commands = []
        def command(self, command, setting=None, value=None):
            self.commands.append((command, setting, value))
            return {'notification': 'ok'}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.toggle_playback()
    controller.toggle_playback()
    controller.stop()
    controller.toggle_shuffle()
    controller.toggle_shuffle()

    assert gateway.commands == [
        ('play', None, None), ('pause', None, None), ('stop', None, None),
        ('set', 'shuffle', 'on'), ('set', 'shuffle', 'off'),
    ]
    assert not controller.state.shuffle_enabled
    controller.close()


def test_view_fills_bars_and_keeps_selection_visible_after_resize():
    class Screen:
        def __init__(self, height, width): self.height, self.width, self.styles = height, width, []
        def erase(self): pass
        def refresh(self): pass
        def getmaxyx(self): return self.height, self.width
        def chgat(self, row, column, width, style): self.styles.append((row, column, width, style))
        def addnstr(self, *_): pass

    state = TuiState(items=[{'spotify_id': str(index), 'name': str(index)} for index in range(10)], selected=9, first_visible=5)
    state.resize(7)
    screen = Screen(7, 40)
    CursesView().draw(screen, state)
    assert (0, 0, 40) == screen.styles[0][:3]
    assert (6, 0, 40) == screen.styles[-1][:3]
    state.resize(4)
    assert state.first_visible == 8
