import curses
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


def test_artist_view_plays_artist_and_then_shows_the_queue():
    class Gateway:
        def __init__(self): self.calls = []
        def play(self, resource_type, value):
            self.calls.append((resource_type, value))
            return {'notification': 'Playback started.'}
        def load(self, resource, value, _):
            self.calls.append(('load', resource, value))
            return {'tracks': []}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.state.select_view(View.ARTISTS)
    controller.state.items = [{'spotify_id': 'artist-id', 'type': 'artists', 'name': 'Artist'}]
    controller.play_selected()
    wait_for_load(controller)

    assert gateway.calls == [('uri', 'spotify:artist:artist-id'), ('load', 'queue', None)]
    assert controller.state.view is View.NOW_PLAYING
    controller.close()


def test_artist_queue_keeps_its_tracks_when_selecting_a_different_track():
    class Gateway:
        def __init__(self): self.play_calls = []
        def play(self, resource_type, value):
            self.play_calls.append((resource_type, value))
            return {'notification': 'Playback started.'}

    controller = TuiController(Gateway())
    controller.state.show_playing_context('spotify:artist:artist-id', 'Artist', 'artist')
    controller.state.items = [{'spotify_id': 'first'}, {'spotify_id': 'selected'}]
    controller.state.selected = 1
    controller.play_selected()
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'selected'}, 'context': None, 'is_playing': True,
    }})
    controller.tick()

    assert controller.gateway.play_calls == [('queue_track', 'spotify:track:selected')]
    assert [item['spotify_id'] for item in controller.state.items] == ['first', 'selected']
    assert controller.state.title == 'Artist'
    assert not controller.state.loading
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


def test_reopened_ui_restores_album_order_and_playing_selection_from_daemon_event():
    album_uri = 'spotify:album:wasteland'
    tracks = [
        {'spotify_id': 'first', 'type': 'tracks', 'name': 'America the Beautiful'},
        {'spotify_id': 'second', 'type': 'tracks', 'name': 'Battle Hymn of the Republic'},
        {'spotify_id': 'third', 'type': 'tracks', 'name': 'Battle Hymn of the Republic - Choir'},
    ]

    class Gateway:
        def __init__(self): self.loads = []
        def load(self, resource, value, _):
            self.loads.append((resource, value))
            assert (resource, value) == ('tracks', album_uri)
            return {'tracks': tracks, 'playing_id': 'third', 'context_name': 'Wasteland 3'}

    gateway = Gateway()
    controller = TuiController(gateway)
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'third'}, 'context': {'uri': album_uri},
    }})
    controller.tick()
    controller.select_view(View.NOW_PLAYING)
    wait_for_load(controller)

    assert gateway.loads == [('tracks', album_uri)]
    assert [item['name'] for item in controller.state.items] == [item['name'] for item in tracks]
    assert controller.state.selected == 2
    assert controller.state.title == 'Wasteland 3'
    controller.close()


def test_reopened_ui_recovers_album_when_spotify_playback_context_is_missing():
    album_uri = 'spotify:album:wasteland'

    class Gateway:
        def __init__(self): self.loads = []
        def load(self, resource, value, _):
            self.loads.append((resource, value))
            if resource == 'queue':
                return {
                    'tracks': [{'spotify_id': 'second'}, {'spotify_id': 'third'}, {'spotify_id': 'first'}],
                    'playing_id': 'second', 'context_uri': album_uri, 'context_name': 'Wasteland 3',
                    'context_tracks': [
                        {'spotify_id': 'first'}, {'spotify_id': 'second'}, {'spotify_id': 'third'},
                    ],
                }
            return {
                'tracks': [{'spotify_id': 'first'}, {'spotify_id': 'second'}, {'spotify_id': 'third'}],
                'playing_id': 'second', 'context_name': 'Wasteland 3',
            }

    gateway = Gateway()
    controller = TuiController(gateway)
    controller.state.view = View.NOW_PLAYING
    controller.start_load()
    wait_for_load(controller)
    assert gateway.loads == [('queue', None)]
    assert [item['spotify_id'] for item in controller.state.items] == ['first', 'second', 'third']
    assert controller.state.selected == 1 and controller.state.title == 'Wasteland 3'
    controller.close()


def test_now_playing_switches_context_and_keeps_it_when_spotify_omits_context():
    class Gateway:
        def load(self, resource, value, _):
            if resource == 'tracks':
                return {'tracks': [{'spotify_id': 'track', 'name': 'Track'}], 'playing_id': 'track', 'context_name': 'Playlist'}
            return {'tracks': [{'spotify_id': 'track', 'name': 'Track'}], 'playing_id': 'track'}

    controller = TuiController(Gateway())
    controller.state.view = View.NOW_PLAYING
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'track'}, 'context': {'uri': 'spotify:playlist:mine'},
    }})
    controller.tick()
    wait_for_load(controller)
    assert controller.state.resource == 'tracks' and controller.state.title == 'Playlist'
    assert controller.state.update_playback_context({'uri': 'spotify:playlist:mine'}) is False
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'different'}, 'context': None,
    }})
    controller.tick()
    assert controller.state.resource == 'tracks' and controller.state.title == 'Playlist'
    assert controller.state.update_playback_context({'uri': None}) is False
    controller.close()


def test_now_playing_keeps_an_album_list_for_an_alternate_track_identifier():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.track_context = TrackContext('spotify:album:selected', 'Selected')
    controller.state.items = [{'spotify_id': 'catalogue-id', 'name': 'Aquadanse'}]
    controller.state.playing_id = 'catalogue-id'

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'playback-variant-id'}, 'context': {'uri': 'spotify:album:selected'},
    }})
    controller.tick()

    assert controller.state.track_context == TrackContext('spotify:album:selected', 'Selected')
    assert controller.state.resource == 'tracks'
    controller.close()


def test_album_view_marks_the_catalogue_track_for_an_alternate_playback_id():
    state = TuiState(track_context=TrackContext('spotify:album:selected', 'Selected'))
    state.items = [
        {'spotify_id': 'first', 'track_number': 1, 'disc_number': 1},
        {'spotify_id': 'catalogue-aquadanse', 'track_number': 2, 'disc_number': 1},
    ]

    state.update_playing_item({'id': 'spotify-playback-variant', 'track_number': 2, 'disc_number': 1})

    assert state.playback_id == 'spotify-playback-variant'
    assert state.playing_id == 'catalogue-aquadanse'


def test_artist_context_uses_queue_and_unsupported_context_clears_it():
    state = TuiState(track_context=TrackContext('spotify:album:old', 'Old album'))
    assert state.update_playback_context({'uri': 'spotify:artist:other'}) is True
    assert state.track_context is None
    assert state.queue_context == TrackContext('spotify:artist:other', 'Now playing')
    assert state.update_playback_context({'uri': 'spotify:artist:other'}) is False
    assert state.update_playback_context({'uri': 'spotify:show:other'}) is True
    assert state.queue_context is None


def test_empty_spotify_event_keeps_artist_queue_playing_marker():
    controller = TuiController()
    controller.state.queue_context = TrackContext('spotify:artist:maddie', 'Maddie Ashman')
    controller.state.playing_id = 'playing'
    controller._events.put({'event': 'state_changed', 'state': {'item': {}, 'context': None}})

    controller.tick()

    assert controller.state.playing_id == 'playing'
    controller.close()


def test_artist_display_context_keeps_the_artist_list_when_spotify_plays_an_album():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.set_queue_context('spotify:artist:artist', 'Artist')
    controller.state.items = [{'spotify_id': 'track', 'name': 'Track'}]
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'track'},
        'context': {'uri': 'spotify:album:album'},
        'display_context': {'uri': 'spotify:artist:artist', 'name': 'Artist'},
    }})

    controller.tick()

    assert controller.state.queue_context.uri == 'spotify:artist:artist'
    assert controller.state.track_context is None
    assert [item['spotify_id'] for item in controller.state.items] == ['track']
    controller.close()


def test_selected_context_ignores_old_playback_context_until_spotify_confirms_it():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.show_playing_context('spotify:album:selected', 'Selected', 'album')
    controller._expect_context('spotify:album:selected')
    reloads = []
    controller.start_load = lambda: reloads.append('load')

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'old'}, 'context': {'uri': 'spotify:playlist:old'},
    }})
    controller.tick()
    assert controller.state.track_context == TrackContext('spotify:album:selected', 'Selected')
    assert reloads == []

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'new'}, 'context': {'uri': 'spotify:album:selected'},
    }})
    controller.tick()
    assert controller._expected_context_uri is None

    controller._expect_context('spotify:album:selected')
    controller._expected_context_deadline = 0
    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'external'}, 'context': {'uri': 'spotify:playlist:external'},
    }})
    controller.tick()
    assert controller.state.track_context == TrackContext('spotify:playlist:external', 'Now playing')
    assert reloads == ['load']
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


def test_view_draws_navigation_tabs_and_a_playback_progress_footer():
    class Screen:
        def __init__(self): self.calls = []
        def erase(self): pass
        def refresh(self): pass
        def getmaxyx(self): return 8, 40
        def chgat(self, *args): self.calls.append(('chgat',) + args)
        def addnstr(self, *args): self.calls.append(('addnstr',) + args)

    screen = Screen()
    state = TuiState(view=View.ARTISTS, is_playing=True, progress_ms=30_000, duration_ms=60_000)
    assert state.title == 'Artists'
    view = CursesView()
    view.bar_style, view.progress_style = 1, 2
    view.draw(screen, state)

    text_calls = [call for call in screen.calls if call[0] == 'addnstr']
    active = next(call for call in text_calls if call[3] == ' 3 Artists ')
    inactive = next(call for call in text_calls if call[3] == ' 1 Albums ')
    assert active[5] != inactive[5]
    passed_time = next(call for call in text_calls if call[3] == '0:30 /')
    remaining_time = next(call for call in text_calls if call[3] == ' 1:00')
    assert (passed_time[2], remaining_time[2]) == (14, 20)
    assert passed_time[5] == view.bar_style
    assert remaining_time[5] == view.progress_style | curses.A_BOLD
    assert all(call[4] <= 39 for call in text_calls if call[1] == 7)


def test_view_formats_collection_rows_for_the_active_view():
    view = CursesView()
    item = {'name': 'Name', 'artists': 'Artist', 'owner': 'Owner', 'followers': 1234}

    assert view._item_label(item, View.ALBUMS) == 'Name  ●  Artist'
    assert view._item_label(item, View.PLAYLISTS) == 'Name'
    assert view._item_label(item, View.ARTISTS) == 'Name'
    assert view._item_label(item, View.NOW_PLAYING) == 'Name  ●  Artist'


def test_view_draws_track_duration_on_the_right_in_now_playing():
    class Screen:
        def __init__(self): self.calls = []
        def erase(self): pass
        def refresh(self): pass
        def getmaxyx(self): return 6, 20
        def chgat(self, *_): pass
        def addnstr(self, *args): self.calls.append(args)

    screen = Screen()
    state = TuiState(
        view=View.NOW_PLAYING,
        items=[{'spotify_id': 'track', 'name': 'A long title', 'artists': 'Artist', 'duration_ms': 243_000}],
    )
    CursesView().draw(screen, state)

    row = [call for call in screen.calls if call[0] == 1]
    title = next(call for call in row if call[2] == '  A long ti...')
    duration = next(call for call in row if call[2] == '4:03')
    assert title[3] == 14
    assert duration[1] == 15


def test_view_truncates_rows_with_an_ellipsis():
    assert CursesView()._truncate('Short', 10) == 'Short'
    assert CursesView()._truncate('Long title', 7) == 'Long...'
    assert CursesView()._truncate('Long title', 2) == '..'


def test_view_keeps_selected_playing_text_dark_and_other_playing_text_bold():
    class Screen:
        def erase(self): pass
        def refresh(self): pass
        def getmaxyx(self): return 6, 40
        def chgat(self, *_): pass
        def addnstr(self, *args): calls.append(args)

    calls = []
    state = TuiState(
        items=[
            {'spotify_id': 'selected', 'name': 'Selected'},
            {'spotify_id': 'playing', 'name': 'Playing'},
        ],
        selected=0,
        playing_id='playing',
        visible_rows=2,
    )
    view = CursesView()
    view.selected_style = 101
    view.draw(Screen(), state)

    selected = next(call for call in calls if 'Selected' in call[2])
    playing = next(call for call in calls if 'Playing' in call[2])
    assert selected[4] == view.selected_style
    assert playing[4] == curses.A_BOLD


def test_view_recalculates_progress_width_after_terminal_resize():
    class Screen:
        def __init__(self):
            self.height, self.width, self.calls = 8, 40, []
        def erase(self): pass
        def refresh(self): pass
        def getmaxyx(self): return self.height, self.width
        def chgat(self, *args): self.calls.append(('chgat',) + args)
        def addnstr(self, *args): self.calls.append(('addnstr',) + args)

    screen = Screen()
    state = TuiState(is_playing=True, progress_ms=30_000, duration_ms=60_000)
    view = CursesView()
    view.bar_style, view.progress_style = 1, 2
    view.draw(screen, state)
    first_fill = [call for call in screen.calls if call[0] == 'chgat' and call[1:4] == (7, 0, 20)]

    screen.width = 60
    screen.calls.clear()
    view.draw(screen, state)
    second_fill = [call for call in screen.calls if call[0] == 'chgat' and call[1:4] == (7, 0, 30)]
    label = next(call for call in screen.calls if call[0] == 'addnstr' and call[3] == '0:30 /')

    assert first_fill
    assert second_fill
    assert label[2] == 24


def test_controller_coalesces_seeks_without_blocking_the_terminal():
    class Gateway:
        def __init__(self): self.commands = []
        def command(self, *args):
            self.commands.append(args)
            return {'notification': 'Seeked.', 'progress_ms': args[2]}

    class DeferredExecutor:
        def submit(self, function, *args): self.work = function, args
        def shutdown(self, **_): pass

    gateway = Gateway()
    controller = TuiController(gateway)
    controller._seeker = DeferredExecutor()
    controller.seek(1)
    assert gateway.commands == []

    controller.state.duration_ms = 60_000
    controller.state.progress_ms = 10_000
    controller.seek(1)
    controller.seek(1)
    assert controller.state.progress_ms == 30_000
    assert gateway.commands == []
    controller._seek_due_at = 0
    controller._dispatch_pending_seek()
    work, args = controller._seeker.work
    work(*args)
    controller._process_seek_results()
    assert gateway.commands == [('seek', None, 30_000)]
    assert controller.state.progress_ms == 30_000
    controller.close()


def test_controller_reports_a_seek_transport_error():
    class Gateway:
        def command(self, *_): raise RuntimeError('offline')

    controller = TuiController(Gateway())
    controller._run_seek(1, 10_000)
    controller._process_seek_results()
    assert controller.state.message == 'Could not seek: offline'
    controller.close()
