import json
import socket
import threading
from importlib.metadata import PackageNotFoundError

import pytest

from common.daemon_client import DaemonClient
from spotify_cmd_ui_client.controller import TuiController
from spotify_cmd_ui_client.gateway import CommandResult, RequestCancellation, SpotifyGateway
from spotify_cmd_ui_client.main import TuiApplication, get_pkg_version, main
from spotify_cmd_ui_client.state import TrackContext, TuiState, View
from spotify_cmd_ui_client.view import CursesView


class FakeClient:
    def __init__(self, response=None):
        self.response = response or {'albums': []}
        self.requests, self.cancelled, self.subscription = [], False, None

    def request(self, payload):
        self.requests.append(payload)
        return self.response

    def request_with_metadata(self, payload):
        self.requests.append(payload)
        return {'payload': self.response, 'state_revision': 4}

    def cancel(self):
        self.cancelled = True

    def subscribe(self, callback, stop_event):
        self.subscription = callback, stop_event


def test_gateway_builds_protocol_requests_and_cancellation_interrupts_client():
    clients = []

    def factory():
        client = FakeClient({'tracks': []})
        clients.append(client)
        return client

    gateway = SpotifyGateway(factory)
    cancellation = RequestCancellation()
    assert gateway.load('tracks', 'spotify:album:x', cancellation) == {'tracks': []}
    assert clients[-1].requests == [{'command': 'get', 'setting': None, 'type': 'tracks', 'value': 'spotify:album:x'}]
    cancellation.cancel()
    assert clients[-1].cancelled
    assert gateway.play('uri', 'spotify:album:x') == {'tracks': []}
    assert clients[-1].requests[-1] == {'command': 'play', 'setting': None, 'type': 'uri', 'value': 'spotify:album:x'}
    assert gateway.command('set', 'shuffle', 'on') == {'tracks': []}
    assert gateway.play_with_state_revision('uri', 'spotify:album:x').state_revision == 4
    assert gateway.command_with_state_revision('pause').payload == {'tracks': []}
    stopped = RequestCancellation()
    stopped.cancel()
    assert gateway.load('albums', None, stopped) is None
    assert clients[-1].cancelled


def test_gateway_subscription_delegates_stop_event():
    client = FakeClient()
    callback, stop_event = object(), threading.Event()
    SpotifyGateway(lambda: client).subscribe(callback, stop_event)
    assert client.subscription == (callback, stop_event)


def test_controller_events_errors_and_failed_load_are_visible():
    class Gateway:
        def load(self, *_):
            raise RuntimeError('offline')

        def subscribe(self, callback, stop):
            self.callback, self.stop = callback, stop

    controller = TuiController(Gateway())
    controller._events.put({'event': 'connection_error', 'error': 'offline'})
    controller._events.put({'event': 'state_changed', 'state': {'item': {'id': 'id'}, 'is_playing': True, 'shuffle_state': True}})
    controller.tick()
    assert controller.state.message == 'offline'
    assert (controller.state.playing_id, controller.state.is_playing, controller.state.shuffle_enabled) == ('id', True, True)
    controller._load(1, 'albums', None, None, RequestCancellation())
    controller._load_token = 1
    controller.tick()
    assert 'Could not load albums' in controller.state.message
    controller.close()


def test_controller_discards_event_at_or_before_its_command_revision():
    controller = TuiController()
    controller.state.accept_state_revision(4)
    controller._events.put({'event': 'state_changed', 'state_revision': 4, 'state': {'item': {'id': 'stale'}}})
    controller._events.put({'event': 'state_changed', 'state_revision': 5, 'state': {'item': {'id': 'fresh'}}})

    controller.tick()

    assert controller.state.playing_id == 'fresh'
    assert controller.state.latest_state_revision == 5
    controller.close()


def test_controller_records_command_response_revision():
    class Gateway:
        def command_with_state_revision(self, *_):
            return CommandResult({'notification': 'paused'}, 6)

    controller = TuiController(Gateway())
    controller.toggle_playback()

    assert controller.state.latest_state_revision == 6
    assert controller.state.message == 'paused'
    controller.close()


def test_controller_ignores_input_while_loading_and_reports_command_error():
    class Gateway:
        def command(self, *_): return {'error': 'denied'}

    controller = TuiController(Gateway())
    controller.state.items = [{'spotify_id': 'x'}]
    controller.state.loading = True
    controller.move(1)
    controller.play_selected()
    controller.toggle_playback()
    assert controller.state.selected == 0
    assert controller.state.message == 'denied'
    controller.close()


def test_controller_subscription_events_context_play_and_stale_results(monkeypatch):
    class Gateway:
        def play(self, *_): return {'notification': 'played'}
        def subscribe(self, *_): pass
    controller = TuiController(Gateway())
    reloads = []
    monkeypatch.setattr(controller, 'start_load', lambda: reloads.append('load'))
    controller.state.view = View.NOW_PLAYING
    controller._events.put({'event': 'connection_restored'})
    controller._events.put({'event': 'ignored'})
    controller._events.put({'event': 'state_changed', 'state': {'item': {'id': 'changed'}}})
    controller.tick()
    assert reloads == ['load', 'load']
    controller.state.track_context = __import__('spotify_cmd_ui_client.state', fromlist=['TrackContext']).TrackContext('spotify:album:a', 'Album')
    controller.state.items = [{'spotify_id': 'track'}]
    controller.play_selected()
    assert controller.state.playing_id == 'track'
    controller._results.put(__import__('spotify_cmd_ui_client.controller', fromlist=['LoadResult']).LoadResult(99, 'albums', None, None, {'albums': []}))
    controller.tick()
    controller.close()


def test_controller_does_not_reload_now_playing_for_progress_events():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.playing_id = 'track'
    controller.state.playback_id = 'track'
    reloads = []
    controller.start_load = lambda: reloads.append('load')

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'track'}, 'progress_ms': 2_000, 'context': None,
    }})
    controller.tick()
    assert reloads == []

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'next'}, 'progress_ms': 0, 'context': None,
    }})
    controller.tick()
    assert reloads == ['load']
    controller.close()


def test_controller_keeps_the_selected_marker_until_spotify_confirms_the_new_track():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.items = [
        {'spotify_id': 'previous', 'track_number': 1, 'disc_number': 1},
        {'spotify_id': 'selected', 'track_number': 2, 'disc_number': 1},
    ]
    controller.state.track_context = TrackContext('spotify:album:album-id', 'Album')
    controller.state.playback_id = controller.state.playing_id = 'previous'
    controller._apply_play({'notification': 'Playback started.'}, 'selected')
    assert controller.state.playback_id == 'selected'

    controller._events.put({'event': 'state_changed', 'state': {'item': {'id': 'previous'}}})
    controller.tick()
    assert controller.state.playing_id == 'selected'
    assert controller.state.expected_playing_id == 'selected'

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'linked-selected', 'linked_from': {'id': 'selected'}, 'track_number': 2, 'disc_number': 1},
    }})
    controller.tick()
    assert controller.state.playback_id == 'linked-selected'
    assert controller.state.playing_id == 'selected'
    assert controller.state.expected_playing_id is None

    controller._apply_play({'notification': 'Playback started.'}, 'selected')
    controller._expected_playing_deadline = 0
    controller._events.put({'event': 'state_changed', 'state': {'item': {'id': 'previous'}}})
    controller.tick()
    assert controller.state.playing_id == 'previous'
    controller.close()


def test_controller_start_resize_and_expected_playback_event(monkeypatch):
    class Gateway:
        def subscribe(self, callback, stop):
            callback({'event': 'state_changed', 'state': {'item': {'id': 'wanted'}}})
    controller = TuiController(Gateway())
    loads = []
    monkeypatch.setattr(controller, 'start_load', lambda: loads.append('load'))
    controller.start()
    controller.resize(12)
    controller.state.expected_playing_id = 'wanted'
    controller.tick()
    assert loads == ['load'] and controller.state.visible_rows == 10 and controller.state.expected_playing_id is None
    controller.state.loading = False
    controller.move(1)
    controller.close()


def test_controller_transition_compatibility_properties_delegate_to_transition():
    controller = TuiController()
    controller._expect_context('spotify:album:album')
    assert controller._expected_context_uri == 'spotify:album:album'
    assert controller._expected_context_deadline is not None
    controller._expected_context_deadline = 0
    controller._expect_playing_item('track')
    assert controller._expected_playing_deadline is not None
    controller._expected_playing_deadline = 0
    controller.close()


def test_controller_reloads_after_spotify_confirms_a_started_playlist(monkeypatch):
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller.state.track_context = TrackContext('spotify:playlist:playlist-id', 'Playlist')
    controller._expect_context('spotify:playlist:playlist-id')
    loads = []
    monkeypatch.setattr(controller, 'start_load', lambda: loads.append('load'))

    controller._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'track'}, 'context': {'uri': 'spotify:playlist:playlist-id'},
    }})
    controller.tick()

    assert loads == ['load']
    controller.close()


def test_state_response_preserves_selection_and_empty_response_is_safe():
    state = TuiState(items=[{'spotify_id': 'old'}], selected=0)
    state.apply_response('albums', {'albums': [{'spotify_id': 'same'}]}, 'same')
    assert state.selected == 0
    state.apply_response('albums', {'albums': []}, None)
    assert state.selected == 0
    state.set_queue_context('spotify:artist:artist', 'Artist')
    assert state.queue_context.name == 'Artist' and state.track_context is None


def test_queue_result_restores_artist_context_from_the_daemon():
    controller = TuiController()
    controller.state.view = View.NOW_PLAYING
    controller._load_token = 1
    controller._results.put(__import__('spotify_cmd_ui_client.controller', fromlist=['LoadResult']).LoadResult(
        1, 'queue', None, None,
        {'tracks': [{'spotify_id': 'track'}], 'playing_id': 'track',
         'artist_context_uri': 'spotify:artist:artist', 'artist_context_name': 'Artist'},
    ))
    controller.tick()
    assert controller.state.title == 'Artist'
    assert controller.state.items == [{'spotify_id': 'track'}]
    controller.close()


class Screen:
    def __init__(self, key=ord('q')):
        self.key, self.calls = key, []

    def timeout(self, value): self.calls.append(('timeout', value))
    def getch(self): return self.key
    def getmaxyx(self): return 8, 40
    def erase(self): pass
    def refresh(self): pass
    def chgat(self, *args): self.calls.append(('chgat', args))
    def addnstr(self, *args): self.calls.append(('addnstr', args))


def test_application_routes_all_keys_and_runs_lifecycle(monkeypatch):
    app = TuiApplication(lambda: FakeClient())
    calls = []
    app.controller.tick = lambda: calls.append('tick')
    app.controller.resize = lambda height: calls.append(('resize', height))
    app.view.draw = lambda screen, state: calls.append('draw')
    for key, expected in ((ord('1'), ('view', 0)), (ord('2'), ('view', 1)), (ord('3'), ('view', 2)), (ord('4'), ('view', 3))):
        app.controller.select_view = lambda value, calls=calls: calls.append(('view', value))
        assert app._handle_key(key)
        assert calls[-1] == expected
    app.controller.move = lambda value: calls.append(('move', value))
    app.controller.play_selected = lambda: calls.append('play')
    app.controller.toggle_playback = lambda: calls.append('toggle')
    app.controller.stop = lambda: calls.append('stop')
    app.controller.seek = lambda value: calls.append(('seek', value))
    app.controller.toggle_shuffle = lambda: calls.append('shuffle')
    import curses
    for key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_ENTER, ord(' '), ord('s'), ord('h'), -1):
        assert app._handle_key(key)
    assert ('seek', -1) in calls and ('seek', 1) in calls
    assert app._handle_key(ord('q')) is False and app._handle_key(27) is False
    app.controller.start = lambda: calls.append('start')
    app.controller.close = lambda: calls.append('close')
    app.view.initialize_colors = lambda: calls.append('colors')
    monkeypatch.setattr('spotify_cmd_ui_client.main.curses.curs_set', lambda _: None)
    screen = Screen()
    app.run(screen)
    assert ('timeout', 100) in screen.calls
    assert 'start' in calls and calls[-1] == 'close'


def test_application_continues_until_cycle_requests_exit(monkeypatch):
    app = TuiApplication(lambda: FakeClient())
    cycles, lifecycle = iter([True, False]), []
    monkeypatch.setattr(app, '_run_cycle', lambda _: next(cycles))
    monkeypatch.setattr(app.controller, 'start', lambda: lifecycle.append('start'))
    monkeypatch.setattr(app.controller, 'close', lambda: lifecycle.append('close'))
    monkeypatch.setattr(app.view, 'initialize_colors', lambda: None)
    monkeypatch.setattr('spotify_cmd_ui_client.main.curses.curs_set', lambda _: None)
    app.run(Screen())
    assert lifecycle == ['start', 'close']


def test_main_uses_curses_wrapper(monkeypatch):
    called = []
    monkeypatch.setattr('spotify_cmd_ui_client.main.curses.wrapper', lambda callback: called.append(callback))
    main([])
    assert len(called) == 1


def test_main_exposes_version_and_help(monkeypatch, capsys):
    monkeypatch.setattr('spotify_cmd_ui_client.main.version', lambda _: '0.9.9')
    assert get_pkg_version() == '0.9.9'
    monkeypatch.setattr(
        'spotify_cmd_ui_client.main.version',
        lambda _: (_ for _ in ()).throw(PackageNotFoundError()),
    )
    assert get_pkg_version() == 'unknown'
    monkeypatch.setattr('spotify_cmd_ui_client.main.get_pkg_version', lambda: '0.9.9')
    main(['--version'])
    assert capsys.readouterr().out == '0.9.9\n'

    with pytest.raises(SystemExit, match='0'):
        main(['--help'])
    assert 'Terminal UI for spotify-cmd.' in capsys.readouterr().out


def test_view_colors_loading_and_curses_errors(monkeypatch):
    import curses
    view = CursesView()
    color_pairs = []
    monkeypatch.setattr(curses, 'has_colors', lambda: True)
    monkeypatch.setattr(curses, 'start_color', lambda: None)
    monkeypatch.setattr(curses, 'use_default_colors', lambda: None)
    monkeypatch.setattr(curses, 'init_pair', lambda *args: color_pairs.append(args))
    monkeypatch.setattr(curses, 'color_pair', lambda pair: pair * 10)
    monkeypatch.setattr(curses, 'COLORS', 16, raising=False)
    view.initialize_colors()
    assert color_pairs[0] == (view.BAR_PAIR, curses.COLOR_BLACK, curses.COLOR_WHITE)
    assert color_pairs[2] == (view.PROGRESS_PAIR, 15, 8)
    assert not view.selected_style & curses.A_BOLD
    class BrokenScreen(Screen):
        def chgat(self, *_): raise curses.error()
    state = TuiState(loading=True)
    view.draw(BrokenScreen(), state)
    monkeypatch.setattr(curses, 'start_color', lambda: (_ for _ in ()).throw(curses.error()))
    CursesView().initialize_colors()
    monkeypatch.setattr(curses, 'has_colors', lambda: False)
    CursesView().initialize_colors()
    state = TuiState(items=[{'spotify_id': 'track', 'name': 'Track', 'artists': 'Artist'}], playing_id='track')
    CursesView().draw(Screen(), state)


class FakeSocket:
    def __init__(self, receive=b''):
        self.receive, self.closed, self.connected = receive, False, []
    def connect(self, address): self.connected.append(address)
    def fileno(self): return -1 if self.closed else 4
    def close(self): self.closed = True
    def shutdown(self, *_): pass


def test_daemon_client_request_success_no_response_and_cancel(monkeypatch):
    sent = []
    sockets = [FakeSocket(), FakeSocket(), FakeSocket()]
    monkeypatch.setattr('common.daemon_client.socket.socket', lambda *_: sockets.pop(0))
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.send_data', lambda sock, message: sent.append(message))
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.receive_data', lambda sock: json.dumps({'payload': {'ok': True}}))
    client = DaemonClient()
    assert client.request({'command': 'get'}) == {'ok': True}
    assert sent
    client = DaemonClient()
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.receive_data', lambda sock: '')
    assert client.request({}) == {'error': 'No response from daemon.'}
    client.cancel()
    assert client.sock.closed


def test_daemon_client_returns_response_state_revision(monkeypatch):
    monkeypatch.setattr('common.daemon_client.socket.socket', lambda *_: FakeSocket())
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.send_data', lambda *_: None)
    response = __import__('common.socket_message', fromlist=['SocketMessage']).SocketMessage(
        'response', {'ok': True}, state_revision=9,
    ).to_json()
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.receive_data', lambda _: response)

    assert DaemonClient().request_with_metadata({'command': 'get'}) == {
        'payload': {'ok': True}, 'state_revision': 9,
    }


def test_daemon_client_reopens_closed_socket_and_returns_protocol_errors(monkeypatch):
    first, replacement = FakeSocket(), FakeSocket()
    first.closed = True
    monkeypatch.setattr('common.daemon_client.socket.socket', lambda *_: replacement)
    client = DaemonClient()
    client.sock = first
    monkeypatch.setattr(client, 'connect', lambda: True)
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.send_data', lambda *_: (_ for _ in ()).throw(socket.error('broken')))
    assert client.request({}) == {'error': 'broken'}
    client.cancel()
    client.cancel()  # cancelling an already closed request is intentionally harmless


def test_daemon_client_cancel_tolerates_shutdown_error_and_subscription_timeout(monkeypatch):
    class ShutdownBroken(FakeSocket):
        def shutdown(self, *_): raise OSError('already disconnected')
    client = DaemonClient()
    client.sock = ShutdownBroken()
    client.cancel()
    class TimeoutThenClose:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def settimeout(self, _): pass
        def connect(self, _): pass
        def recv(self, _):
            if not hasattr(self, 'timed_out'):
                self.timed_out = True
                raise socket.timeout()
            return b''
    sockets = iter([FakeSocket(), TimeoutThenClose()])
    monkeypatch.setattr('common.daemon_client.socket.socket', lambda *_: next(sockets))
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.send_data', lambda *_: None)
    stop = threading.Event()
    client = DaemonClient()
    client.subscribe(lambda _: stop.set(), stop)


def test_daemon_client_subscribe_reports_decode_and_connection_errors(monkeypatch):
    class SubscriptionSocket:
        def __init__(self): self.closed = False
        def __enter__(self): return self
        def __exit__(self, *_): self.closed = True
        def settimeout(self, _): pass
        def connect(self, _): pass
        def recv(self, _): return b'{invalid}' + __import__('common.socket_data_handler', fromlist=['SocketDataHandler']).SocketDataHandler.END_OF_MESSAGE
    class StopAfterRetry(threading.Event):
        def wait(self, timeout=None):
            self.set()
            return True
    stop, events = StopAfterRetry(), []
    created = [FakeSocket(), SubscriptionSocket()]
    monkeypatch.setattr('common.daemon_client.socket.socket', lambda *_: created.pop(0))
    monkeypatch.setattr('common.daemon_client.SocketDataHandler.send_data', lambda *_: None)
    client = DaemonClient()
    def callback(event): events.append(event)
    client.subscribe(callback, stop)
    assert events == [{'event': 'connection_error', 'error': 'Cannot connect to daemon.'}]
