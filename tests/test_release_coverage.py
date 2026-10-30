import importlib
import socket

import pytest

from common.config import Config
from common.socket_data_handler import SocketDataHandler
from spotify_cmd_client import main as client_main
from spotify_cmd_daemon.socket_server import SocketServer
from spotify_cmd_daemon import main as daemon_main


def test_config_remaining_paths(monkeypatch):
    Config._instance = object()
    with pytest.raises(Exception, match='singleton'):
        Config()
    Config._instance = None
    monkeypatch.setattr(Config, '_find_config_file', lambda self: None)
    with pytest.raises(Exception, match='Config file not found'):
        Config.get_instance()
    Config._instance = None
    monkeypatch.undo()
    monkeypatch.setattr('os.path.exists', lambda path: False)
    assert Config._find_config_file(Config.__new__(Config)) is None


def test_client_version_fallback_and_connection_failure(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    monkeypatch.setattr(client_main, 'version', lambda _: (_ for _ in ()).throw(PackageNotFoundError()))
    assert client_main.get_pkg_version() == 'unknown'
    class Client:
        def execute(self, _): return {'error': 'offline'}
        def render(self, response, output_format): assert response == {'error': 'offline'} and output_format == 'text'
    monkeypatch.setattr(client_main, 'Client', Client)
    monkeypatch.setattr('sys.argv', ['spotify-cmd', 'pause'])
    client_main.main()


def test_pagination_album_shape():
    from spotify_cmd_daemon.operations.helpers.get_resource_from_library import get_resource_from_library
    result = get_resource_from_library(
        lambda **kwargs: {'items': [{'album': {'name': 'wanted'}}]}, 'wanted', is_album=True
    )
    assert result == {'name': 'wanted'}


def test_socket_server_error_paths(monkeypatch, tmp_path):
    server = SocketServer(object())
    server.server_address = str(tmp_path / 'missing.sock')
    server.cleanup_socket()
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.os.path.exists', lambda path: True)
    monkeypatch.setattr('spotify_cmd_daemon.socket_server.os.remove', lambda path: (_ for _ in ()).throw(FileNotFoundError()))
    server.cleanup_socket()
    class BrokenSocket:
        def bind(self, path): raise OSError('cannot bind')
        def close(self): pass
    monkeypatch.setattr(socket, 'socket', lambda *args: BrokenSocket())
    monkeypatch.setattr('sys.exit', lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit):
        server.start_server()

    server = SocketServer(object())
    monkeypatch.setattr(SocketDataHandler, 'receive_data', lambda *_: None)
    server.handle_connection(object())
    monkeypatch.setattr(SocketDataHandler, 'receive_data', lambda *_: (_ for _ in ()).throw(ValueError('bad packet')))
    server.handle_connection(object())
    server.stop_server()


def test_daemon_stale_lock_remove_error_and_default_failure(monkeypatch, tmp_path):
    lock = tmp_path / 'lock'
    lock.write_text('123')
    monkeypatch.setattr(daemon_main, 'lock_file', str(lock))
    monkeypatch.setattr(daemon_main, '_pid_is_running', lambda pid: False)
    original_remove = daemon_main.os.remove
    calls = []
    def remove(path):
        if not calls:
            calls.append(path)
            raise OSError('race')
        original_remove(path)
    monkeypatch.setattr(daemon_main.os, 'remove', remove)
    daemon_main.ensure_lock()
    assert lock.exists()
    lock.unlink()
