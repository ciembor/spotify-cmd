import shutil
import subprocess
import sys
import os

import pytest

from spotify_cmd_daemon.mpris import MprisPlayer, MprisService
from spotify_cmd_daemon.spotify_controller import SpotifyController
from spotify_cmd_daemon import main as daemon_main


class Controller:
    def __init__(self):
        self.commands = []
        self.state = {
            'is_playing': True, 'progress_ms': 1234, 'shuffle_state': True,
            'volume_percent': 25,
            'item': {
                'id': 'track-1', 'name': 'Track', 'duration_ms': 180000,
                'artists': [{'name': 'Artist'}], 'album': {'name': 'Album'},
                'external_urls': {'spotify': 'https://open.spotify.com/track/track-1'},
            },
        }
    def get_playback_state(self): return self.state
    def execute_command(self, message): self.commands.append(message.payload['command'])


def test_mpris_player_maps_state_and_controls():
    controller = Controller()
    player = MprisPlayer(controller)
    assert player.PlaybackStatus == 'Playing'
    assert player.Position == 1_234_000
    assert player.Volume == 0.25
    assert player.Shuffle is True
    metadata = player.Metadata
    assert metadata['xesam:title'].value == 'Track'
    assert metadata['xesam:artist'].value == ['Artist']
    assert metadata['mpris:length'].value == 180_000_000
    player.Play(); player.Pause(); player.Next(); player.Previous()
    controller.state['is_playing'] = False
    player.PlayPause()
    assert controller.commands == ['play', 'pause', 'next', 'previous', 'play']


def test_mpris_empty_state_is_stopped():
    controller = Controller()
    controller.state['item'] = {}
    controller.state['is_playing'] = False
    player = MprisPlayer(controller)
    assert player.PlaybackStatus == 'Stopped'
    assert player.Metadata == {}


def test_mpris_service_connects_exports_and_starts_thread(monkeypatch):
    import spotify_cmd_daemon.mpris as module
    events = []
    class Bus:
        async def connect(self): return self
        async def request_name(self, name): events.append(('name', name))
        def export(self, path, player): events.append(('export', path, player))
    monkeypatch.setattr(module, 'MessageBus', lambda **kwargs: Bus())
    class Finished:
        def __await__(self): return iter(())
    monkeypatch.setattr(module.asyncio, 'Future', Finished)
    service = MprisService(Controller(), 'org.mpris.MediaPlayer2.test')
    import asyncio
    asyncio.run(service.serve())
    assert events[0] == ('name', 'org.mpris.MediaPlayer2.test')
    class Thread:
        def __init__(self, target, daemon): self.target, self.daemon, self.started = target, daemon, False
        def start(self): self.started = True
    monkeypatch.setattr(module.threading, 'Thread', Thread)
    service.start()
    assert service.thread.daemon and service.thread.started


def test_controller_playback_state_and_daemon_mpris_start(monkeypatch):
    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = type('Spotify', (), {
        'current_playback': lambda self: {
            'is_playing': True, 'progress_ms': 500, 'shuffle_state': True,
            'device': {'volume_percent': 30}, 'item': {'id': 'track'},
        }
    })()
    assert controller.get_playback_state() == {
        'is_playing': True, 'progress_ms': 500, 'shuffle_state': True,
        'volume_percent': 30, 'item': {'id': 'track'},
    }
    started = []
    controller.config = type('Config', (), {'mpris_enabled': True, 'mpris_bus_name': 'org.mpris.MediaPlayer2.test'})()
    server = type('Server', (), {'spotify_controller': controller, 'start_server': lambda self: None})()
    monkeypatch.setattr(daemon_main, 'ensure_lock', lambda: None)
    monkeypatch.setattr(daemon_main, 'create_server', lambda: server)
    monkeypatch.setattr(daemon_main, 'install_signal_handlers', lambda server: None)
    monkeypatch.setattr(daemon_main, 'MprisService', lambda *args: type('Service', (), {'start': lambda self: started.append(args)})())
    daemon_main.run_server_foreground()
    assert started == [(controller, 'org.mpris.MediaPlayer2.test')]


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('dbus-run-session'), reason='Linux D-Bus session is required')
def test_mpris_dbus_round_trip():
    script = '''
import asyncio
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
from spotify_cmd_daemon.mpris import MprisPlayer, OBJECT_PATH
class Controller:
    def get_playback_state(self): return {'is_playing': False, 'progress_ms': 0, 'shuffle_state': False, 'volume_percent': 0, 'item': {}}
    def execute_command(self, message): assert message.payload['command'] == 'play'
async def main():
    server = await MessageBus(bus_type=BusType.SESSION).connect()
    await server.request_name('org.mpris.MediaPlayer2.spotify_cmd_test')
    server.export(OBJECT_PATH, MprisPlayer(Controller()))
    client = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await client.introspect('org.mpris.MediaPlayer2.spotify_cmd_test', OBJECT_PATH)
    obj = client.get_proxy_object('org.mpris.MediaPlayer2.spotify_cmd_test', OBJECT_PATH, introspection)
    player = obj.get_interface('org.mpris.MediaPlayer2.Player')
    assert await player.get_playback_status() == 'Stopped'
    await player.call_play()
asyncio.run(main())
'''
    result = subprocess.run(
        ['dbus-run-session', '--', sys.executable, '-c', script],
        capture_output=True, text=True, env=os.environ | {'PYTHONPATH': 'src'},
    )
    assert result.returncode == 0, result.stderr
