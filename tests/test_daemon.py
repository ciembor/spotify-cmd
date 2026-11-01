import sys

import pytest

from common.socket_message import SocketMessage
from spotify_cmd_daemon import main as daemon_main
from spotify_cmd_daemon.playback_session import PlaybackSession
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
    assert controller.device_name == 'Office'
    spotify.device_data[0]['is_active'] = False
    controller.ensure_device_active(force_play=True)
    assert spotify.calls[-1] == ('transfer', {'device_id': 'id', 'force_play': True})
    spotify.device_data = []
    with pytest.raises(Exception, match="Device 'Office' not found"):
        controller.ensure_device_active(retries=1, delay=0)


def test_controller_stays_available_when_device_disappears(monkeypatch, caplog):
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.time.sleep', lambda _: None)
    controller, spotify = make_controller(monkeypatch, FakeSpotify([]))
    assert controller.device_id is None
    assert 'unavailable at startup' in caplog.text

    response = controller.execute_command(SocketMessage('request', {'command': 'pause'}))
    assert 'error' in response

    spotify.device_data = [{'id': 'reconnected', 'name': 'Office', 'is_active': True}]
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_queue', lambda _: {'tracks': []})
    response = controller.execute_command(SocketMessage('request', {'command': 'get', 'type': 'queue'}))
    assert controller.device_id == 'reconnected'
    assert response == {'tracks': []}


def test_controller_routes_commands_and_returns_errors(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    monkeypatch.setattr(controller, 'ensure_device_active', lambda **kwargs: None)
    called = []
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.pause_playback', lambda *args: {'notification': 'paused'})
    assert controller.execute_command(SocketMessage('request', {'command': 'pause'})) == {'notification': 'paused'}
    monkeypatch.setattr(controller, 'handle_play', lambda data: (_ for _ in ()).throw(ValueError('bad command')))
    assert controller.execute_command(SocketMessage('request', {'command': 'play'})) == {'error': 'bad command'}
    assert controller.execute_command(SocketMessage('request', {'command': 'unknown'})) == {'error': 'Unsupported command: unknown'}
    assert controller.handle_set({'setting': 'unknown'}) == {'error': 'Unsupported setting: unknown'}
    assert controller.handle_get({'type': 'unknown'}) == {'error': 'Unsupported resource: unknown'}


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


def test_artist_queue_waits_for_the_requested_context_and_survives_lost_context(monkeypatch):
    class Api:
        def __init__(self): self.playback = {'item': {'id': 'first', 'artists': [{'id': 'maddie'}]}}
        def current_playback(self): return self.playback

    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = Api()
    controller.session = PlaybackSession()
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.time.sleep', lambda _: None)
    controller._start_artist_queue('spotify:artist:maddie', 'Maddie Ashman')
    assert controller.session.artist_queue().uri == 'spotify:artist:maddie'
    assert controller.session.artist_queue().pending

    tracks = [{'spotify_id': 'first'}, {'spotify_id': 'second'}]
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_queue', lambda _: {'tracks': tracks, 'playing_id': 'first'})
    response = controller._get_queue()
    assert response['artist_context_name'] == 'Maddie Ashman'
    controller.spotipy_client.playback = {'context': {'uri': 'spotify:artist:maddie'}, 'item': {'id': 'first'}}
    response = controller._get_queue()
    assert response['tracks'] == tracks

    controller.spotipy_client.playback = {'item': {'id': 'second'}}
    response = controller._get_queue()
    assert response['tracks'] == tracks and response['playing_id'] == 'second'

    controller.spotipy_client.playback = {'context': {'uri': 'spotify:album:other'}, 'item': {'id': 'outside'}}
    response = controller._get_queue()
    assert response == {'tracks': tracks, 'playing_id': 'first'} and controller.session.artist_queue() is None

    controller.spotipy_client.playback = {'item': {'id': 'wrong', 'artists': []}}
    controller._start_artist_queue('spotify:artist:missing', 'Missing')
    assert controller._get_queue() == {'error': 'Spotify did not start the selected artist.'}
    assert controller._is_artist_playing({'context': {'uri': 'spotify:artist:maddie'}}, 'spotify:artist:maddie')


def test_artist_queue_keeps_its_initial_order_when_spotify_rotates_it(monkeypatch):
    class Api:
        def current_playback(self):
            return {'context': {'uri': 'spotify:artist:maddie'}, 'item': {'id': 'second'}}

    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = Api()
    controller.session = PlaybackSession()
    queue = controller.session.begin_artist_queue('spotify:artist:maddie', 'Maddie Ashman')
    controller.session.complete_artist_queue(queue, [{'spotify_id': 'first'}, {'spotify_id': 'second'}])
    monkeypatch.setattr(
        'spotify_cmd_daemon.spotify_controller.operations.get_queue',
        lambda _: {'tracks': [{'spotify_id': 'second'}, {'spotify_id': 'first'}], 'playing_id': 'second'},
    )

    response = controller._get_queue()

    assert [track['spotify_id'] for track in response['tracks']] == ['first', 'second']
    assert response['playing_id'] == 'second'


def test_playback_session_replaces_and_clears_artist_queues_safely():
    session = PlaybackSession()
    first = session.begin_artist_queue('spotify:artist:first', None)
    assert first.name == 'Now playing' and first.pending
    completed = session.complete_artist_queue(first, [{'spotify_id': 'track'}])
    assert completed.tracks == ({'spotify_id': 'track'},) and not completed.pending

    second = session.begin_artist_queue('spotify:artist:second', 'Second')
    assert session.complete_artist_queue(first, []) is None
    session.clear_artist_queue(first)
    assert session.artist_queue() == second
    session.clear_artist_queue()
    assert session.artist_queue() is None


def test_artist_queue_does_not_overwrite_a_newer_artist_session(monkeypatch):
    class Api:
        def current_playback(self):
            return {'item': {'artists': [{'id': 'first'}]}}

    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = Api()
    controller.session = PlaybackSession()
    queue = controller._start_artist_queue('spotify:artist:first', 'First')

    def queue_from_api(_):
        controller.session.begin_artist_queue('spotify:artist:second', 'Second')
        return {'tracks': [{'spotify_id': 'track'}], 'playing_id': 'track'}

    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.get_queue', queue_from_api)
    assert controller._wait_for_artist_queue(queue) == {'tracks': [{'spotify_id': 'track'}], 'playing_id': 'track'}
    assert controller.session.artist_queue().uri == 'spotify:artist:second'


def test_queue_track_uses_the_artist_context_held_by_the_session(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    controller.session.begin_artist_queue('spotify:artist:maddie', 'Maddie Ashman')
    queue = controller.session.artist_queue()
    controller.session.complete_artist_queue(queue, [{'spotify_id': 'track'}])
    received = []
    monkeypatch.setattr(
        'spotify_cmd_daemon.spotify_controller.operations.play_queue_track',
        lambda *args: received.append(args) or {'notification': 'started'},
    )

    response = controller.handle_play({'type': 'queue_track', 'value': 'spotify:track:track'})

    assert response == {'notification': 'started'}
    assert received[0][-2] == 'spotify:artist:maddie'
    assert received[0][-1] == ({'spotify_id': 'track'},)
    assert controller.session.artist_queue() is None


def test_starting_a_non_artist_context_clears_the_artist_session(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    controller.session.begin_artist_queue('spotify:artist:maddie', 'Maddie Ashman')
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.get_resource_uri', lambda *_: 'spotify:album:new')
    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.start_playback', lambda *_: {'notification': 'started'})

    controller.handle_play({'type': 'album', 'value': 'New album'})

    assert controller.session.artist_queue() is None


def test_playback_state_exposes_artist_display_context_for_an_album_track(monkeypatch):
    class Api:
        def current_playback(self):
            return {
                'is_playing': True,
                'item': {'id': 'track'},
                'context': {'uri': 'spotify:album:album'},
            }

    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = Api()
    controller.session = PlaybackSession()
    queue = controller.session.begin_artist_queue('spotify:artist:artist', 'Artist')
    controller.session.complete_artist_queue(queue, [{'spotify_id': 'track'}])

    state = controller.get_playback_state()

    assert state['context'] == {'uri': 'spotify:album:album'}
    assert state['display_context'] == {'uri': 'spotify:artist:artist', 'name': 'Artist'}


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


@pytest.mark.parametrize('raises', [False, True])
def test_failed_artist_track_selection_keeps_session(monkeypatch, raises):
    controller, _ = make_controller(monkeypatch)
    pending = controller.session.begin_artist_queue('spotify:artist:artist', 'Artist')
    queue = controller.session.complete_artist_queue(pending, [{'spotify_id': 'track'}])

    def fail(*args):
        if raises:
            raise RuntimeError('Playback rejected')
        return {'error': 'Playback rejected'}

    monkeypatch.setattr('spotify_cmd_daemon.spotify_controller.operations.play_queue_track', fail)
    if raises:
        with pytest.raises(RuntimeError, match='Playback rejected'):
            controller.handle_play({'type': 'queue_track', 'value': 'spotify:track:track'})
    else:
        assert controller.handle_play({'type': 'queue_track', 'value': 'spotify:track:track'}) == {
            'error': 'Playback rejected',
        }
    assert controller.session.artist_queue() == queue
