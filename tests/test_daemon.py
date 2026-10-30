import sys

import pytest

from common.socket_message import SocketMessage
from spotify_cmd_daemon import main as daemon_main
from spotify_cmd_daemon.spotify_controller import SpotifyController


class FakeSpotify:
    def __init__(self, devices=None):
        self.device_data = devices if devices is not None else [{'id': 'id', 'name': 'Office', 'is_active': True}]
        self.calls = []
    def devices(self): return {'devices': self.device_data}
    def transfer_playback(self, **kwargs): self.calls.append(('transfer', kwargs))


def make_controller(monkeypatch, spotify=None):
    spotify = spotify or FakeSpotify()
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.SpotifyOAuth', lambda **kwargs: kwargs)
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.spotipy.Spotify', lambda **kwargs: spotify)
    return SpotifyController(), spotify


def test_controller_device_selection_and_retry(monkeypatch):
    controller, spotify = make_controller(monkeypatch)
    assert controller.device_id == 'id'
    controller.device_name = 'Office'
    spotify.device_data[0]['is_active'] = False
    controller.ensure_device_active(force_play=True)
    assert spotify.calls[-1] == ('transfer', {'device_id': 'id', 'force_play': True})
    spotify.device_data = []
    with pytest.raises(Exception, match="Device 'Office' not found"):
        controller.ensure_device_active(retries=1, delay=0)


def test_controller_routes_commands_and_returns_errors(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    monkeypatch.setattr(controller, 'ensure_device_active', lambda **kwargs: None)
    called = []
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.pause_playback', lambda *args: {'notification': 'paused'})
    controller.execute_command(SocketMessage('request', {'command': 'pause'}))
    assert controller.get_response().payload == {'notification': 'paused'}
    monkeypatch.setattr(controller, 'handle_play', lambda data: (_ for _ in ()).throw(ValueError('bad command')))
    controller.execute_command(SocketMessage('request', {'command': 'play'}))
    assert controller.get_response().payload == {'error': 'bad command'}


def test_controller_routes_context_queue_and_library_getters(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    monkeypatch.setattr(controller, 'ensure_device_active', lambda **kwargs: None)
    calls = []
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.start_playback', lambda *args: calls.append(('context', args)) or {'notification': 'ok'})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.play_queue_track', lambda *args: calls.append(('queue', args)) or {'notification': 'ok'})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_queue', lambda *_: {'tracks': []})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_context_tracks', lambda *_: {'tracks': []})
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.stop_playback', lambda *_: {'notification': 'stopped'})
    controller.execute_command(SocketMessage('request', {'command': 'stop'}))
    controller.execute_command(SocketMessage('request', {'command': 'play', 'type': 'context', 'value': {'uri': 'spotify:album:a', 'offset': 2}}))
    controller.execute_command(SocketMessage('request', {'command': 'play', 'type': 'queue_track', 'value': 'spotify:track:t'}))
    controller.execute_command(SocketMessage('request', {'command': 'get', 'type': 'queue'}))
    controller.execute_command(SocketMessage('request', {'command': 'get', 'type': 'tracks', 'value': 'spotify:album:a'}))
    assert [name for name, _ in calls] == ['context', 'queue']


def test_daemon_main_modes_and_lock_lifecycle(monkeypatch, tmp_path, capsys):
    lock = tmp_path / 'daemon.lock'
    monkeypatch.setattr(daemon_main, 'lock_file', str(lock))
    daemon_main.ensure_lock()
    assert lock.read_text() == str(__import__('os').getpid())
    monkeypatch.setattr(daemon_main, '_pid_is_running', lambda pid: True)
    with pytest.raises(SystemExit):
        daemon_main.ensure_lock()
    capsys.readouterr()
    lock.unlink()
    monkeypatch.setattr(daemon_main, 'get_pkg_version', lambda: '2.0')
    monkeypatch.setattr(sys, 'argv', ['daemon', '--version'])
    daemon_main.main()
    assert capsys.readouterr().out == '2.0\n'
    calls = []
    monkeypatch.setattr(daemon_main, 'run_server_foreground', lambda: calls.append('foreground'))
    monkeypatch.setattr(sys, 'argv', ['daemon', '--foreground'])
    daemon_main.main()
    assert calls == ['foreground']
