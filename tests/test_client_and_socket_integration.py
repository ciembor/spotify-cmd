import json
import os
import socket
import threading

import pytest

from common.socket_data_handler import SocketDataHandler
from common.socket_message import SocketMessage
from spotify_cmd_client.client import Client
from spotify_cmd_client.data_presenter import DataPresenter
from spotify_cmd_client import main as client_main
from spotify_cmd_daemon.socket_server import SocketServer


class FakeSocket:
    def __init__(self, error=None):
        self.error = error
        self.connected_to = None
        self.closed = False

    def connect(self, address):
        if self.error:
            raise self.error
        self.connected_to = address

    def close(self):
        self.closed = True


def test_client_connect_send_and_rendering(monkeypatch, capsys):
    client = Client()
    sock = FakeSocket()
    client.sock = sock
    assert client.connect()
    assert sock.connected_to == client.server_address

    sent = []
    monkeypatch.setattr(SocketDataHandler, 'send_data', lambda connection, data: sent.append(json.loads(data)))
    client.send_command({'command': 'pause'})
    assert sent[0]['payload'] == {'command': 'pause'}

    response = SocketMessage('response', {'notification': 'done'}).to_json()
    monkeypatch.setattr(SocketDataHandler, 'receive_data', lambda connection: response)
    client.handle_response('text')
    assert capsys.readouterr().out == 'done\n'
    client.handle_response('json')
    assert json.loads(capsys.readouterr().out) == {'notification': 'done'}
    client.handle_response('verbose')
    assert json.loads(capsys.readouterr().out)['message_type'] == 'response'
    client.close()
    assert sock.closed


def test_client_reports_socket_errors(monkeypatch, capsys):
    client = Client()
    client.sock = FakeSocket(OSError('offline'))
    assert not client.connect()
    monkeypatch.setattr(SocketDataHandler, 'send_data', lambda *_: (_ for _ in ()).throw(OSError('write failed')))
    client.send_command({})
    monkeypatch.setattr(SocketDataHandler, 'receive_data', lambda *_: (_ for _ in ()).throw(OSError('read failed')))
    client.handle_response('text')
    output = capsys.readouterr().out
    assert 'Cannot connect' in output and 'Error sending' in output and 'Error receiving' in output


def test_data_presenter_formats_collections_and_errors(capsys):
    DataPresenter.print_output({'error': 'bad'})
    DataPresenter.print_output({'notification': 'ok'})
    DataPresenter.print_output({'albums': [{'artists': 'A', 'name': 'B', 'spotify_id': 'id'}]})
    output = capsys.readouterr().out
    assert 'Error: bad' in output and 'ok' in output and 'spotify:album:id' in output


def test_cli_builds_payloads_preserving_zero_and_version(monkeypatch, capsys):
    calls = []
    class FakeClient:
        def connect(self): return True
        def send_command(self, payload): calls.append(payload)
        def handle_response(self, output_format): calls.append(output_format)
        def close(self): calls.append('closed')
    monkeypatch.setattr(client_main, 'Client', FakeClient)
    monkeypatch.setattr(client_main, 'get_pkg_version', lambda: '1.2.3')
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'set', 'volume', '0'])
    client_main.main()
    assert calls[0]['value'] == 0
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'version'])
    client_main.main()
    assert capsys.readouterr().out == '1.2.3\n'


def test_socket_server_end_to_end_with_real_unix_socket(tmp_path):
    class Controller:
        def __init__(self): self.payload = None
        def execute_command(self, message): self.payload = message.payload
        def get_response(self): return SocketMessage('response', {'notification': 'handled'})

    controller = Controller()
    server = SocketServer(controller)
    server.server_address = f'/tmp/spotify-cmd-{os.getpid()}.sock'
    thread = threading.Thread(target=server.start_server, daemon=True)
    thread.start()

    for _ in range(50):
        if os.path.exists(server.server_address):
            break
        threading.Event().wait(0.01)

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(server.server_address)
        SocketDataHandler.send_data(client, SocketMessage('request', {'command': 'pause'}).to_json())
        response = SocketMessage.from_json(SocketDataHandler.receive_data(client))
        assert response.payload == {'notification': 'handled'}
        assert controller.payload == {'command': 'pause'}
    finally:
        client.close()
        server.stop_server()
        thread.join(timeout=1)
    assert not thread.is_alive()
