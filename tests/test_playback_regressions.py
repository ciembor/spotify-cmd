import pytest

from spotify_cmd_daemon.operations.play_queue_track import play_queue_track
from spotify_cmd_daemon.operations.get_context_tracks import get_context_tracks
from spotify_cmd_ui_client.state import TuiState, TrackContext
from spotify_cmd_ui_client.view import CursesView


def test_album_uses_account_market_to_match_playback_id():
    class API:
        def album(self, _):
            return {'name': 'EP'}

        def album_tracks(self, _, **kwargs):
            assert kwargs['market'] == 'from_token'
            return {'items': [{'id': 'available', 'name': 'Track', 'artists': [],
                               'linked_from': {'id': 'catalogue'}}]}

        def current_playback(self):
            return {'item': {'id': 'available'}}
    response = get_context_tracks(API(), 'spotify:album:ep')
    state = TuiState(track_context=TrackContext('spotify:album:ep', 'EP'))
    state.apply_response('tracks', response, None)
    assert state.playing_id == state.items[0]['spotify_id'] == 'available'
    state.update_playing_item({'id': 'available'})
    assert state.playing_id == 'available'


@pytest.mark.parametrize('notification', ['Playback of resource started.', 'Seeked to 28s.'])
def test_success_notification_does_not_replace_progress(monkeypatch, notification):
    state = TuiState(is_playing=True, duration_ms=100000, progress_ms=28000)
    state.set_response_message({'notification': notification})
    view = CursesView()
    calls = []
    monkeypatch.setattr(view, '_draw_progress', lambda *args: calls.append(args))
    view._draw_footer(object(), state, 20, 80)
    assert len(calls) == 1


@pytest.mark.parametrize('album,playable', [(None, True), ('spotify:album:a', False)])
def test_artist_selection_rejects_unavailable_album_without_mutating_queue(album, playable):
    class API:
        def track(self, uri, **kwargs):
            return {'album': {'uri': album}, 'is_playable': playable}
    result = play_queue_track(API(), 'device', 'spotify:track:b', 'spotify:artist:a', ({'spotify_id': 'b'},))
    assert 'unavailable' in result['error']


def test_artist_selection_starts_exact_album_track_without_queue_mutations():
    class API:
        def __init__(self):
            self.calls = []

        def track(self, uri, **kwargs):
            assert uri == 'spotify:track:b'
            assert kwargs == {'market': 'from_token'}
            return {'uri': 'spotify:track:replacement', 'album': {'uri': 'spotify:album:a'}}

        def start_playback(self, **kwargs):
            self.calls.append(kwargs)

    api = API()
    result = play_queue_track(api, 'device', 'spotify:track:b', 'spotify:artist:a', ({'spotify_id': 'b'},))
    assert 'error' not in result
    assert api.calls == [{'context_uri': 'spotify:album:a', 'offset': {'uri': 'spotify:track:replacement'},
                          'device_id': 'device', 'position_ms': 0}]


@pytest.mark.parametrize('resource', ['album', 'playlist'])
def test_selecting_context_track_keeps_context_and_resets_position(resource):
    class API:
        def current_playback(self):
            return {'context': {'uri': f'spotify:{resource}:existing'}, 'progress_ms': 90000}

        def start_playback(self, **kwargs):
            self.arguments = kwargs

    api = API()
    result = play_queue_track(api, 'device', 'spotify:track:selected')
    assert 'error' not in result
    assert api.arguments == {
        'context_uri': f'spotify:{resource}:existing', 'offset': {'uri': 'spotify:track:selected'},
        'device_id': 'device', 'position_ms': 0,
    }


def test_artist_selection_event_loads_album_once_and_keeps_playing_marker(monkeypatch):
    from spotify_cmd_ui_client.controller import TuiController
    from spotify_cmd_ui_client.state import View

    class Gateway:
        def play(self, resource, value):
            assert (resource, value) == ('queue_track', 'spotify:track:selected')
            return {'notification': 'Playback started from the track album.'}

    controller = TuiController(Gateway())
    try:
        state = controller.state
        state.view = View.NOW_PLAYING
        state.set_queue_context('spotify:artist:artist', 'Artist')
        state.items = [{'spotify_id': 'old'}, {'spotify_id': 'selected'}]
        state.selected = 1
        state.playing_id = state.playback_id = 'old'
        loads = []
        monkeypatch.setattr(controller, 'start_load', lambda: loads.append(state.resource_value))
        controller.play_selected()
        for track, context in [('old', 'artist:artist'), ('selected', 'album:album'),
                               ('selected', 'album:album')]:
            controller._events.put({'event': 'state_changed', 'state': {
                'item': {'id': track}, 'context': {'uri': f'spotify:{context}'}, 'is_playing': True,
            }})
            controller.tick()
            assert state.playing_id == 'selected'
        assert loads == ['spotify:album:album']
        assert state.queue_context is None
        assert state.track_context.uri == 'spotify:album:album'
        assert state.is_playing
    finally:
        controller.close()
