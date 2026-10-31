import importlib
import os
import sys

import pytest
from spotipy.exceptions import SpotifyException

from common.config import Config
from spotify_cmd_daemon import main as daemon_main
from spotify_cmd_daemon import operations
from spotify_cmd_daemon.operations.helpers.get_album import get_album
from spotify_cmd_daemon.operations.helpers.get_playlist import get_playlist
from spotify_cmd_daemon.operations.helpers.check_resource_existence import check_resource_existence
from spotify_cmd_daemon.spotify_controller import SpotifyController


def test_common_package_and_config_platform_paths(monkeypatch):
    import common
    assert common.config is not None
    config = Config.__new__(Config)
    monkeypatch.setattr('platform.system', lambda: 'Linux')
    assert config._default_socket_path() == '/run/spotify-cmd/spotify-cmd.sock'
    monkeypatch.setattr('platform.system', lambda: 'Darwin')
    assert config._default_socket_path() == '/tmp/spotify-cmd-daemon.sock'


def test_library_helpers_success_and_not_found(monkeypatch):
    album_module = importlib.import_module('spotify_cmd_daemon.operations.helpers.get_album')
    playlist_module = importlib.import_module('spotify_cmd_daemon.operations.helpers.get_playlist')
    monkeypatch.setattr(album_module, 'get_resource_from_library', lambda *args, **kwargs: {'name': 'A'})
    monkeypatch.setattr(playlist_module, 'get_resource_from_library', lambda *args, **kwargs: {'name': 'P'})
    assert album_module.get_album(object(), 'A')['name'] == 'A'
    client = type('Client', (), {'current_user_playlists': lambda *args, **kwargs: None})()
    assert playlist_module.get_playlist(client, 'P')['name'] == 'P'
    monkeypatch.setattr(album_module, 'get_resource_from_library', lambda *args, **kwargs: None)
    monkeypatch.setattr(playlist_module, 'get_resource_from_library', lambda *args, **kwargs: None)
    with pytest.raises(Exception, match="Album 'A'"):
        album_module.get_album(object(), 'A')
    with pytest.raises(Exception, match="Playlist 'P'"):
        playlist_module.get_playlist(client, 'P')


def test_existence_helper_api_errors():
    class Api:
        def track(self, uri): raise SpotifyException(404, -1, 'missing')
        def album(self, uri): raise SpotifyException(500, -1, 'broken')
        def playlist(self, uri): raise SpotifyException(404, -1, 'missing')
        def artist(self, uri): raise SpotifyException(404, -1, 'missing')
    api = Api()
    assert not check_resource_existence(api, 'track', 'x')
    assert not check_resource_existence(api, 'playlist', 'x')
    assert not check_resource_existence(api, 'artist', 'x')
    with pytest.raises(SpotifyException):
        check_resource_existence(api, 'album', 'x')


def test_operations_preserve_nonempty_spotify_responses():
    class Api:
        def __getattr__(self, name):
            return lambda **kwargs: {'api': name}
    api = Api()
    assert operations.pause_playback(api, 'd') == {'api': 'pause_playback'}
    assert operations.next_track(api, 'd') == {'api': 'next_track'}
    assert operations.previous_track(api, 'd') == {'api': 'previous_track'}
    assert operations.resume_playback(api, 'd') == {'api': 'start_playback'}
    assert operations.set_shuffle(api, 'd', 'off') == {'api': 'shuffle'}
    assert operations.set_volume(api, 'd', 50) == {'api': 'volume'}
    api.current_playback = lambda: {'progress_ms': 0, 'item': {'duration_ms': 1_000}}
    api.seek_track = lambda _position_ms, **_kwargs: {'api': 'seek_track'}
    assert operations.seek_playback(api, 'd', 500) == {'api': 'seek_track', 'progress_ms': 500}


def make_controller(monkeypatch):
    class Api:
        def __init__(self): self.devices_data = [{'id': 'active', 'name': 'Active', 'is_active': True}]
        def devices(self): return {'devices': self.devices_data}
    api = Api()
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.SpotifyOAuth', lambda **kwargs: kwargs)
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.spotipy.Spotify', lambda **kwargs: api)
    return SpotifyController(), api


def test_controller_refresh_fallbacks_and_command_routing(monkeypatch):
    controller, api = make_controller(monkeypatch)
    api.devices_data = [{'id': 'first', 'name': 'First', 'is_active': False}]
    controller.device_name = None
    assert controller.refresh_device_id()['id'] == 'first'
    api.devices_data = []
    with pytest.raises(Exception, match='No active'):
        controller.refresh_device_id()
    with pytest.raises(Exception, match='could not be activated'):
        controller.ensure_device_active(retries=0, delay=0)

    controller.device_id = 'd'
    monkeypatch.setattr(controller, 'ensure_device_active', lambda **kwargs: None)
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.next_track', lambda *args: {'notification': 'next'})
    controller.execute_command(type('Message', (), {'payload': {'command': 'next'}})())
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.previous_track', lambda *args: {'notification': 'previous'})
    controller.execute_command(type('Message', (), {'payload': {'command': 'previous'}})())
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.seek_playback', lambda *args: {'notification': 'seek'})
    controller.execute_command(type('Message', (), {'payload': {'command': 'seek', 'value': 10_000}})())
    for command, handler in [('play', 'handle_play'), ('set', 'handle_set'), ('get', 'handle_get'), ('find', 'handle_search')]:
        seen = []
        monkeypatch.setattr(controller, handler, lambda payload, seen=seen: seen.append(payload))
        controller.execute_command(type('Message', (), {'payload': {'command': command}})())
        assert seen == [{'command': command}]


def test_controller_handlers_and_spotify_errors(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    controller.device_id = 'd'
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.get_resource_uri', lambda *args: 'spotify:album:a')
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.start_playback', lambda *args: {'notification': 'play'})
    assert controller.handle_play({'type': 'album', 'value': 'Album'}) == {'notification': 'play'}
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.get_resource_uri', lambda *args: 'spotify:artist:maddie')
    artist_queues = []
    monkeypatch.setattr(controller, '_start_artist_queue', lambda uri, name: artist_queues.append((uri, name)))
    controller.handle_play({'type': 'artist', 'value': 'Maddie Ashman'})
    assert artist_queues == [('spotify:artist:maddie', 'Maddie Ashman')]
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.resume_playback', lambda *args: {'notification': 'resume'})
    assert controller.handle_play({}) == {'notification': 'resume'}
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.set_shuffle', lambda *args: {'notification': 'shuffle'})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.set_volume', lambda *args: {'notification': 'volume'})
    controller.handle_set({'setting': 'shuffle', 'value': 'on'})
    assert controller.handle_set({'setting': 'volume', 'value': 1}) == {'notification': 'volume'}
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_library_albums', lambda *args: {'albums': []})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_library_playlists', lambda *args: {'playlists': []})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_library_artists', lambda *args: {'artists': []})
    controller.handle_get({'type': 'albums'})
    controller.handle_get({'type': 'playlists'})
    assert controller.handle_get({'type': 'artists'}) == {'artists': []}
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.search', lambda *args: {'tracks': []})
    assert controller.handle_search({'type': 'track', 'value': 'x'}) == {'tracks': []}

    monkeypatch.setattr(controller, 'ensure_device_active', lambda **kwargs: (_ for _ in ()).throw(SpotifyException(400, -1, 'bad request')))
    response = controller.execute_command(type('Message', (), {'payload': {'command': 'pause'}})())
    assert 'bad request' in response['error']


def test_daemon_process_helpers(monkeypatch, tmp_path):
    class Server:
        def __init__(self): self.stopped = False
        def stop_server(self): self.stopped = True
    server = Server()
    lock = tmp_path / 'lock'
    lock.write_text('x')
    monkeypatch.setattr(daemon_main, 'lock_file', str(lock))
    monkeypatch.setattr(daemon_main.sys, 'exit', lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit):
        daemon_main.signal_handler(None, None, server)
    assert server.stopped and not lock.exists()
    monkeypatch.setattr(daemon_main.os, 'kill', lambda *args: None)
    assert daemon_main._pid_is_running(1)
    monkeypatch.setattr(daemon_main.os, 'kill', lambda *args: (_ for _ in ()).throw(ProcessLookupError()))
    assert not daemon_main._pid_is_running(1)
    monkeypatch.setattr(daemon_main.os, 'kill', lambda *args: (_ for _ in ()).throw(PermissionError()))
    assert daemon_main._pid_is_running(1)


def test_daemon_server_start_helpers(monkeypatch):
    class Server:
        def start_server(self): pass
    monkeypatch.setattr(daemon_main, 'ensure_lock', lambda: None)
    monkeypatch.setattr(daemon_main, 'create_server', Server)
    monkeypatch.setattr(daemon_main, 'install_signal_handlers', lambda server: None)
    daemon_main.run_server_foreground()
    class Context:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(daemon_main.daemon, 'DaemonContext', Context)
    daemon_main.run_server_daemon()


def test_daemon_utility_paths(monkeypatch, tmp_path):
    class Server:
        def __init__(self, spotify): self.spotify = spotify
        def stop_server(self): pass
    monkeypatch.setattr(daemon_main, 'SpotifyController', lambda: 'spotify')
    monkeypatch.setattr(daemon_main, 'SocketServer', Server)
    assert daemon_main.create_server().spotify == 'spotify'
    installed = []
    monkeypatch.setattr(daemon_main.signal, 'signal', lambda signal, handler: installed.append(signal))
    daemon_main.install_signal_handlers(object())
    assert len(installed) == 2
    monkeypatch.setattr(daemon_main, 'version', lambda _: '1')
    assert daemon_main.get_pkg_version() == '1'
    from importlib.metadata import PackageNotFoundError
    monkeypatch.setattr(daemon_main, 'version', lambda _: (_ for _ in ()).throw(PackageNotFoundError()))
    assert daemon_main.get_pkg_version() == 'unknown'
    lock = tmp_path / 'stale'
    lock.write_text('not-a-pid')
    monkeypatch.setattr(daemon_main, 'lock_file', str(lock))
    daemon_main.ensure_lock()
    assert lock.read_text() == str(os.getpid())
    monkeypatch.setattr(sys, 'argv', ['daemon'])
    called = []
    monkeypatch.setattr(daemon_main, 'run_server_daemon', lambda: called.append(True))
    daemon_main.main()
    assert called
