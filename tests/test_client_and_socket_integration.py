import json
import os
import socket
import threading

import pytest

from common.socket_data_handler import SocketDataHandler
from common.socket_message import SocketMessage
from common.daemon_client import DaemonClient
from common.protocol import CommandRequest, ProtocolError
from spotify_cmd_client.client import Client
from spotify_cmd_client.data_presenter import DataPresenter
from spotify_cmd_client import main as client_main
from spotify_cmd_daemon.socket_server import SocketServer
from spotify_cmd_ui_client.controller import TuiController
from spotify_cmd_ui_client.gateway import SpotifyGateway
from spotify_cmd_ui_client.state import View


def socket_is_listening(address):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        try:
            probe.connect(address)
            return True
        except OSError:
            return False


class FakeSocket:
    def __init__(self, error=None):
        self.error = error
        self.connected_to = None
        self.closed = False

    def connect(self, address):
        if self.error:
            raise self.error
        self.connected_to = address

    def fileno(self):
        return 1

    def close(self):
        self.closed = True


def test_cli_client_delegates_to_shared_transport_and_renders(capsys):
    class Daemon:
        def request(self, payload):
            assert payload == {'command': 'pause'}
            return {'notification': 'done'}

    client = Client(Daemon())
    assert client.execute({'command': 'pause'}) == {'notification': 'done'}
    client.render({'notification': 'done'}, 'text')
    assert capsys.readouterr().out == 'done\n'
    client.render({'notification': 'done'}, 'json')
    assert json.loads(capsys.readouterr().out) == {'notification': 'done'}
    client.render({'notification': 'done'}, 'verbose')
    assert json.loads(capsys.readouterr().out)['message_type'] == 'response'


def test_shared_transport_reports_socket_errors(monkeypatch):
    client = DaemonClient()
    client.sock = FakeSocket(OSError('offline'))
    assert client.request({'command': 'pause'}) == {'error': 'Cannot connect to daemon.'}


def test_subscription_recovers_when_daemon_socket_appears():
    address = f'/tmp/spotify-cmd-sub-{os.getpid()}.sock'
    client = DaemonClient()
    client.server_address = address
    events = []
    disconnected = threading.Event()
    received = threading.Event()
    stop = threading.Event()

    def on_event(event):
        events.append(event)
        if event.get('event') == 'connection_error':
            disconnected.set()
        if event.get('event') == 'state_changed':
            received.set()

    thread = threading.Thread(target=client.subscribe, args=(on_event, stop))
    thread.start()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert disconnected.wait(2)
        server.bind(address)
        server.listen(1)
        server.settimeout(3)
        connection, _ = server.accept()
        with connection:
            request = SocketMessage.from_json(SocketDataHandler.receive_data(connection))
            assert request.payload == {'command': 'subscribe'}
            SocketDataHandler.send_data(connection, SocketMessage('event', {
                'event': 'state_changed', 'state': {'item': {'id': 'track'}},
            }).to_json())
            assert received.wait(2)
        assert [event['event'] for event in events[:3]] == [
            'connection_error', 'connection_restored', 'state_changed',
        ]
    finally:
        stop.set()
        server.close()
        thread.join(timeout=2)
        if os.path.exists(address):
            os.unlink(address)
    assert not thread.is_alive()


def test_data_presenter_formats_collections_and_errors(capsys):
    DataPresenter.print_output({'error': 'bad'})
    DataPresenter.print_output({'notification': 'ok'})
    DataPresenter.print_output({'albums': [{'artists': 'A', 'name': 'B', 'spotify_id': 'id'}]})
    DataPresenter.print_output({'artists': [{'name': 'A', 'followers': 7, 'spotify_id': 'id'}]})
    output = capsys.readouterr().out
    assert 'Error: bad' in output and 'ok' in output and 'spotify:album:id' in output and 'spotify:artist:id' in output


def test_cli_builds_payloads_preserving_zero_and_version(monkeypatch, capsys):
    calls = []
    class FakeClient:
        def execute(self, payload): calls.append(payload); return {'notification': 'ok'}
        def render(self, response, output_format): calls.append((response, output_format))
    monkeypatch.setattr(client_main, 'Client', FakeClient)
    monkeypatch.setattr(client_main, 'get_pkg_version', lambda: '1.2.3')
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'set', 'volume', '0'])
    client_main.main()
    assert calls[0]['value'] == 0
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'version'])
    client_main.main()
    assert capsys.readouterr().out == '1.2.3\n'
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'play', 'artist', 'Artist'])
    client_main.main()
    assert calls[-2]['type'] == 'artist' and calls[-2]['value'] == 'Artist'


def test_socket_server_end_to_end_with_real_unix_socket(tmp_path):
    class Controller:
        def __init__(self): self.payload = None
        def execute_command(self, message):
            self.payload = message.payload
            return {'notification': 'handled'}

    controller = Controller()
    server = SocketServer(controller)
    server.server_address = f'/tmp/spotify-cmd-{os.getpid()}.sock'
    thread = threading.Thread(target=server.start_server, daemon=True)
    thread.start()

    for _ in range(50):
        if socket_is_listening(server.server_address):
            break
        threading.Event().wait(0.01)

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        for _ in range(50):
            try:
                client.connect(server.server_address)
                break
            except ConnectionRefusedError:
                threading.Event().wait(0.01)
        else:
            raise AssertionError('Server did not begin accepting connections')
        SocketDataHandler.send_data(client, SocketMessage('request', {'command': 'pause'}).to_json())
        response = SocketMessage.from_json(SocketDataHandler.receive_data(client))
        assert response.payload == {'notification': 'handled'}
        assert response.state_revision >= 0
        assert controller.payload == {'command': 'pause'}
    finally:
        client.close()
        server.stop_server()
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_socket_server_rejects_an_invalid_command_payload(tmp_path):
    class Controller:
        def execute_command(self, _):
            raise AssertionError('Invalid requests must not reach the controller')

    server = SocketServer(Controller())
    server.server_address = f'/tmp/spotify-cmd-invalid-{os.getpid()}.sock'
    thread = threading.Thread(target=server.start_server, daemon=True)
    thread.start()
    for _ in range(50):
        if socket_is_listening(server.server_address):
            break
        threading.Event().wait(0.01)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(server.server_address)
        SocketDataHandler.send_data(client, SocketMessage('request', {'command': 1}).to_json())
        response = SocketMessage.from_json(SocketDataHandler.receive_data(client))
        assert response.payload == {'error': "Request requires a non-empty 'command' string."}
    finally:
        client.close()
        server.stop_server()
        thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.mark.parametrize('payload, field', [
    ({'command': 'set', 'setting': 1}, 'setting'),
    ({'command': 'get', 'type': 1}, 'type'),
])
def test_command_request_validates_optional_string_fields(payload, field):
    with pytest.raises(ProtocolError, match=field):
        CommandRequest.from_payload(payload)


def test_command_request_preserves_the_wire_payload_shape():
    request = CommandRequest.from_payload({'command': 'pause'})
    assert request.to_payload() == {'command': 'pause', 'setting': None, 'type': None, 'value': None}


def test_socket_server_keeps_concurrent_command_responses_with_their_request():
    address = f'/tmp/spotify-cmd-concurrent-{os.getpid()}.sock'
    slow_started = threading.Event()
    release_slow = threading.Event()

    class Controller:
        def execute_command(self, message):
            value = message.payload['value']
            if value == 'slow':
                slow_started.set()
                assert release_slow.wait(2)
            return {'request': value}

        def get_playback_state(self):
            return {'item': {}}

    server = SocketServer(Controller())
    server.server_address = address
    server_thread = threading.Thread(target=server.start_server, daemon=True)
    server_thread.start()

    def request(value, results):
        client = DaemonClient()
        client.server_address = address
        results[value] = client.request({'command': 'get', 'type': 'queue', 'value': value})

    results = {}
    try:
        for _ in range(100):
            if socket_is_listening(address):
                break
            threading.Event().wait(0.01)
        slow = threading.Thread(target=request, args=('slow', results))
        slow.start()
        assert slow_started.wait(2)
        fast = threading.Thread(target=request, args=('fast', results))
        fast.start()
        fast.join(timeout=2)
        assert results['fast'] == {'request': 'fast'}
        release_slow.set()
        slow.join(timeout=2)
        assert results['slow'] == {'request': 'slow'}
    finally:
        release_slow.set()
        server.stop_server()
        server_thread.join(timeout=2)
        if os.path.exists(address):
            os.unlink(address)


def test_socket_server_serializes_event_writes_to_each_subscriber():
    class Controller:
        def get_playback_state(self):
            return {'item': {'id': 'track'}}

    class Connection:
        def __init__(self):
            self.lock = threading.Lock()
            self.active_writes = 0
            self.max_active_writes = 0

        def sendall(self, _):
            with self.lock:
                self.active_writes += 1
                self.max_active_writes = max(self.max_active_writes, self.active_writes)
            threading.Event().wait(0.01)
            with self.lock:
                self.active_writes -= 1

    server = SocketServer(Controller())
    connection = Connection()
    server.subscribers.add(connection)
    first = threading.Thread(target=server.publish_state, kwargs={'force': True})
    second = threading.Thread(target=server.publish_state, kwargs={'force': True})
    first.start()
    second.start()
    first.join()
    second.join()

    assert connection.max_active_writes == 1


def test_socket_server_does_not_repeat_an_unchanged_event():
    class Controller:
        def get_playback_state(self):
            return {'is_playing': True, 'item': {'id': 'track'}}

    class Connection:
        def __init__(self):
            self.writes = 0

        def sendall(self, _):
            self.writes += 1

    server = SocketServer(Controller())
    connection = Connection()
    server.subscribers.add(connection)

    server.publish_state()
    first_event_writes = connection.writes
    server.publish_state()

    assert first_event_writes > 0
    assert connection.writes == first_event_writes


def test_socket_server_does_not_publish_for_playback_progress_only():
    state = {
        'is_playing': True,
        'shuffle_state': False,
        'volume_percent': 20,
        'item': {'id': 'track'},
        'progress_ms': 1_000,
    }
    progressed_state = {**state, 'progress_ms': 2_000}
    next_track_state = {**state, 'item': {'id': 'next-track'}}
    next_album_state = {**state, 'context': {'uri': 'spotify:album:another'}}

    assert SocketServer.event_state(state) != SocketServer.event_state(progressed_state)
    assert SocketServer.event_state(state) != SocketServer.event_state(next_track_state)
    assert SocketServer.event_state(state) != SocketServer.event_state(next_album_state)


@pytest.mark.parametrize('spotify_context_available,inline_context_tracks', [
    (True, False), (False, True), (False, False),
])
def test_reopened_ui_restores_album_view_through_real_daemon_socket(spotify_context_available, inline_context_tracks):
    address = f'/tmp/spotify-cmd-reopen-{os.getpid()}.sock'
    album_uri = 'spotify:album:wasteland'
    tracks = [
        {'spotify_id': 'first', 'name': 'First'},
        {'spotify_id': 'playing', 'name': 'Playing'},
        {'spotify_id': 'last', 'name': 'Last'},
    ]

    class Controller:
        def get_playback_state(self):
            context = {'uri': album_uri} if spotify_context_available else {}
            return {'item': {'id': 'playing'}, 'context': context, 'is_playing': True}

        def execute_command(self, message):
            payload = message.payload
            if payload['type'] == 'tracks':
                assert payload['value'] == album_uri
                return {'tracks': tracks, 'playing_id': 'playing', 'context_name': 'Wasteland 3'}
            if payload['type'] == 'queue':
                response = {
                    'tracks': tracks[1:] + tracks[:1], 'playing_id': 'playing',
                    'context_uri': album_uri, 'context_name': 'Wasteland 3',
                }
                if inline_context_tracks:
                    response['context_tracks'] = tracks
                return response
            return {'albums': []}

    server = SocketServer(Controller())
    server.server_address = address
    server_thread = threading.Thread(target=server.start_server, daemon=True)
    server_thread.start()

    def client_factory():
        client = DaemonClient()
        client.server_address = address
        return client

    def wait_until(predicate):
        for _ in range(200):
            if predicate():
                return
            threading.Event().wait(0.01)
        raise AssertionError('TUI did not receive album context from daemon')

    try:
        wait_until(lambda: os.path.exists(address))
        for _ in range(2):
            ui = TuiController(SpotifyGateway(client_factory))
            try:
                ui.start()
                def context_received():
                    ui.tick()
                    return ui.state.track_context is not None
                if spotify_context_available:
                    wait_until(context_received)
                ui.select_view(View.NOW_PLAYING)
                def album_loaded():
                    ui.tick()
                    return not ui.state.loading and ui.state.title == 'Wasteland 3'
                wait_until(album_loaded)
                assert [item['spotify_id'] for item in ui.state.items] == ['first', 'playing', 'last']
                assert ui.state.selected == 1
            finally:
                ui.close()
    finally:
        server.stop_server()
        server_thread.join(timeout=2)
        if os.path.exists(address):
            os.unlink(address)


def test_socket_server_subscription_cleanup_and_failed_event_delivery(monkeypatch):
    class Controller:
        def get_playback_state(self): return {'item': {'id': 'track'}}
    class Connection:
        def __init__(self): self.closed = False
        def close(self): self.closed = True
    server = SocketServer(Controller())
    broken = Connection()
    server.subscribers.add(broken)
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.SocketDataHandler.send_data', lambda *_: (_ for _ in ()).throw(OSError('gone')))
    server.publish_state(force=True)
    assert broken not in server.subscribers
    connection = Connection()
    message = SocketMessage('request', {'command': 'subscribe'}).to_json()
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.SocketDataHandler.receive_data', lambda _: message)
    monkeypatch.setattr(server, 'publish_state', lambda force=False: force)
    server.handle_connection(connection)
    assert connection in server.subscribers and not connection.closed
    server.stop_server()
    assert connection.closed and not server.subscribers


@pytest.mark.parametrize('command, response', [
    ('play', {'notification': 'Playing'}),
    ('seek', {'notification': 'Seeked.', 'progress_ms': 10_000}),
])
def test_socket_server_defers_state_publish_after_asynchronous_playback_commands(monkeypatch, command, response):
    class Controller:
        def execute_command(self, _): return response

    class Connection:
        def close(self): pass

    server = SocketServer(Controller())
    message = SocketMessage('request', {'command': command, 'type': 'uri', 'value': 'spotify:track:x'}).to_json()
    published = []
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.SocketDataHandler.receive_data', lambda _: message)
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.SocketDataHandler.send_data', lambda *_: None)
    monkeypatch.setattr(server, 'publish_state', lambda: published.append(True))

    server.handle_connection(Connection())

    assert published == []
    assert server.pending_seek_target == (10_000 if command == 'seek' else None)


def test_socket_server_holds_stale_seek_state_until_spotify_confirms_or_times_out():
    server = SocketServer(object())
    assert not server.should_defer_seek_state({'progress_ms': 1_000})

    server.defer_stale_seek_states(10_000)
    assert server.should_defer_seek_state({'progress_ms': 1_000})
    assert not server.should_defer_seek_state({'progress_ms': 10_500})

    server.defer_stale_seek_states(10_000)
    server.pending_seek_deadline = 0
    assert not server.should_defer_seek_state({'progress_ms': 1_000})


def test_socket_server_poller_skips_stale_seek_state(monkeypatch):
    class Controller:
        def __init__(self): self.calls = 0
        def get_playback_state(self):
            self.calls += 1
            if self.calls == 2:
                server._stop_event.set()
            return {'progress_ms': 1_000 if self.calls == 1 else 10_000, 'item': {'id': 'track'}}

    controller = Controller()
    server = SocketServer(controller)
    server.sock = object()
    server.defer_stale_seek_states(10_000)
    published = []
    monkeypatch.setattr(server, 'publish_state', lambda state: published.append(state))

    server.poll_state()

    assert published == [{'progress_ms': 10_000, 'item': {'id': 'track'}}]


def test_socket_server_poll_publishes_changes_and_survives_state_errors(monkeypatch):
    class Controller:
        def __init__(self): self.calls = 0
        def get_playback_state(self):
            self.calls += 1
            if self.calls == 1: raise RuntimeError('temporary')
            server._stop_event.set()
            return {'item': {'id': 'track'}}
    server = SocketServer(Controller())
    server.sock = object()
    published = []
    monkeypatch.setattr(server, 'publish_state', lambda state: published.append(state))
    server.poll_state()
    assert published == [{'item': {'id': 'track'}}]  # first poll failed but loop stayed alive


def test_socket_server_handles_accept_and_close_errors(monkeypatch):
    class BrokenAcceptSocket:
        instances = 0

        def __init__(self):
            self.calls = 0
            type(self).instances += 1
            self.stop_before_error = type(self).instances > 1

        def bind(self, _): pass
        def listen(self, _): pass
        def settimeout(self, _): pass
        def accept(self):
            self.calls += 1
            if self.calls == 1:
                raise socket.timeout()
            if self.stop_before_error:
                server._stop_event.set()
            raise OSError('accept failed')
        def close(self): raise OSError('already closed')

    class Controller:
        def get_playback_state(self):
            return {'item': {}}

    server = SocketServer(Controller())
    monkeypatch.setattr(socket, 'socket', lambda *_: BrokenAcceptSocket())
    server.start_server()
    server.start_server()

    class BrokenConnection:
        def close(self): raise OSError('already closed')

    server.subscribers.add(BrokenConnection())
    server.stop_server()
