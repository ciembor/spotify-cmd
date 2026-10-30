import json
import os
import socket

import pytest

from config import Config
from socket_data_handler import SocketDataHandler
from socket_message import SocketMessage


@pytest.fixture(autouse=True)
def reset_config():
    Config._instance = None
    yield
    Config._instance = None


def test_config_reads_explicit_file_and_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / 'config.ini'
    config_file.write_text('[SPOTIFY]\nclient_id = id\nclient_secret = secret\n')
    monkeypatch.setenv('SPOTIFY_CMD_CONFIG', str(config_file))

    config = Config.get_instance()

    assert config.config_path == str(config_file)
    assert config.config_dir == str(tmp_path)
    assert config.spotify_redirect_uri == 'http://localhost:8888/callback'
    assert config.socket_buffer_size == 1024
    assert Config.get_instance() is config


def test_config_errors_do_not_leave_a_broken_singleton(monkeypatch):
    monkeypatch.setattr(Config, '_find_config_file', lambda self: None)

    with pytest.raises(Exception, match='Config file not found'):
        Config.get_instance()
    with pytest.raises(Exception, match='Config file not found'):
        Config.get_instance()


def test_config_validation_and_locations(tmp_path, monkeypatch):
    config_file = tmp_path / 'config.ini'
    config_file.write_text('[SPOTIFY]\nclient_id = id\n')
    monkeypatch.setenv('SPOTIFY_CMD_CONFIG', str(config_file))
    with pytest.raises(Exception, match='client_id'):
        Config.get_instance()

    Config._instance = None
    monkeypatch.setattr(os.path, 'exists', lambda path: path == '/etc/spotify-cmd/config.ini')
    assert Config._find_config_file(Config.__new__(Config)) == '/etc/spotify-cmd/config.ini'


def test_socket_message_round_trip():
    message = SocketMessage('request', {'command': 'pause'}, 'client')
    decoded = SocketMessage.from_json(message.to_json())

    assert decoded.message_type == 'request'
    assert decoded.payload == {'command': 'pause'}
    assert decoded.app_id == 'client'
    assert decoded.message_id == message.message_id
    assert decoded.timestamp == message.timestamp


def test_socket_data_handler_handles_chunking_and_eof(monkeypatch):
    left, right = socket.socketpair()
    monkeypatch.setattr(SocketDataHandler, 'SOCKET_BUFFER_SIZE', 3)
    try:
        SocketDataHandler.send_data(left, 'abcdefgh')
        assert SocketDataHandler.receive_data(right) == 'abcdefgh'
        left.close()
        assert SocketDataHandler.receive_data(right) is None
    finally:
        right.close()


def test_socket_data_handler_ignores_empty_messages():
    class Connection:
        def __init__(self):
            self.sent = []

        def sendall(self, value):
            self.sent.append(value)

    connection = Connection()
    SocketDataHandler.send_data(connection, '')
    assert connection.sent == []
