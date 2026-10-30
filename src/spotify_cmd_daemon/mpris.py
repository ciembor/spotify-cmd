import asyncio
import threading

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

from common.socket_message import SocketMessage


OBJECT_PATH = '/org/mpris/MediaPlayer2'


class MprisPlayer(ServiceInterface):
    def __init__(self, controller):
        super().__init__('org.mpris.MediaPlayer2.Player')
        self.controller = controller

    def _state(self):
        return self.controller.get_playback_state()

    def _command(self, command):
        self.controller.execute_command(SocketMessage('request', {'command': command}))
        self.emit_properties_changed({'PlaybackStatus': self.PlaybackStatus})

    @method()
    def Play(self):
        self._command('play')

    @method()
    def Pause(self):
        self._command('pause')

    @method()
    def Stop(self):
        self._command('stop')

    @method()
    def PlayPause(self):
        self._command('pause' if self._state()['is_playing'] else 'play')

    @method()
    def Next(self):
        self._command('next')

    @method()
    def Previous(self):
        self._command('previous')

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> 's':
        state = self._state()
        return 'Playing' if state['is_playing'] else ('Paused' if state['item'] else 'Stopped')

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> 'a{sv}':
        item = self._state()['item']
        if not item:
            return {}
        track_id = item.get('id', 'unknown').replace('-', '_')
        metadata = {
            'mpris:trackid': Variant('o', f'/org/spotify_cmd/track/{track_id}'),
            'xesam:title': Variant('s', item.get('name', '')),
            'xesam:artist': Variant('as', [artist['name'] for artist in item.get('artists', [])]),
            'mpris:length': Variant('x', int(item.get('duration_ms', 0) * 1000)),
        }
        if item.get('album', {}).get('name'):
            metadata['xesam:album'] = Variant('s', item['album']['name'])
        if item.get('external_urls', {}).get('spotify'):
            metadata['xesam:url'] = Variant('s', item['external_urls']['spotify'])
        return metadata

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> 'x':
        return int(self._state()['progress_ms'] * 1000)

    @dbus_property(access=PropertyAccess.READ)
    def Volume(self) -> 'd':
        return self._state()['volume_percent'] / 100

    @dbus_property(access=PropertyAccess.READ)
    def Shuffle(self) -> 'b':
        return self._state()['shuffle_state']

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> 'b': return True
    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> 'b': return True
    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> 'b': return True
    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> 'b': return True
    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> 'b': return True
    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> 'b': return False


class MprisService:
    def __init__(self, controller, bus_name):
        self.controller = controller
        self.bus_name = bus_name
        self.thread = None

    async def serve(self):
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        await bus.request_name(self.bus_name)
        bus.export(OBJECT_PATH, MprisPlayer(self.controller))
        await asyncio.Future()

    def start(self):
        self.thread = threading.Thread(target=lambda: asyncio.run(self.serve()), daemon=True)
        self.thread.start()
