from spotify_cmd_daemon.operations.get_artist_albums import get_artist_albums
from spotify_cmd_ui_client.controller import LoadResult, TuiController
from spotify_cmd_ui_client.state import View


def test_artist_discography_fetches_all_pages():
    class API:
        def artist_albums(self, uri, **kwargs):
            assert uri == 'spotify:artist:a'
            assert kwargs['country'] == 'from_token'
            assert kwargs['album_type'] == 'album,single,compilation'
            offset = kwargs['offset']
            return {'items': [{'id': str(offset), 'name': 'Album', 'artists': [{'name': 'Artist'}]}],
                    'next': 'next-page' if offset == 0 else None}
    response = get_artist_albums(API(), 'spotify:artist:a')
    assert [item['spotify_id'] for item in response['artist_albums']] == ['0', '1']
    assert all(item['type'] == 'albums' for item in response['artist_albums'])


def test_browsing_and_back_during_load_ignore_stale_results(monkeypatch):
    controller = TuiController()
    try:
        state = controller.state
        state.view = View.ARTISTS
        artists = [{'spotify_id': 'a', 'name': 'A'}, {'spotify_id': 'b', 'name': 'B'}]
        state.items = artists
        state.selected = state.first_visible = 1
        loads = []
        monkeypatch.setattr(controller, 'start_load', lambda: loads.append((state.resource, state.resource_value)))
        controller.play_selected()
        assert state.view is View.ARTISTS
        assert loads == [('artist_albums', 'spotify:artist:b')]
        token = controller._load_token
        assert controller.navigate_back()
        controller._results.put(LoadResult(token, 'artist_albums', 'spotify:artist:b', None,
                                            {'artist_albums': [{'spotify_id': 'album'}]}))
        controller.tick()
        assert state.items == artists
        assert state.selected == state.first_visible == 1
        assert state.resource == 'artists'
        assert not controller.navigate_back()
    finally:
        controller.close()


def test_selecting_artist_album_starts_album_and_opens_tracks(monkeypatch):
    class Gateway:
        def play(self, kind, value):
            assert (kind, value) == ('uri', 'spotify:album:album')
            return {'notification': 'started'}

    controller = TuiController(Gateway())
    try:
        state = controller.state
        state.view = View.ARTISTS
        state.items = [{'spotify_id': 'artist', 'name': 'Artist'}]
        monkeypatch.setattr(controller, 'start_load', lambda: None)
        controller.play_selected()
        state.apply_response('artist_albums', {'artist_albums': [
            {'spotify_id': 'album', 'name': 'Album', 'type': 'albums'}]}, None)
        controller.play_selected()
        assert state.view is View.NOW_PLAYING
        assert state.track_context.uri == 'spotify:album:album'
        controller.select_view(View.ARTISTS)
        assert state.resource == 'artists'
        assert state.resource_value is None
        assert not controller.navigate_back()
    finally:
        controller.close()


def test_daemon_routes_artist_albums_request():
    from spotify_cmd_daemon.spotify_controller import SpotifyController

    class API:
        def artist_albums(self, uri, **kwargs):
            assert uri == 'spotify:artist:empty'
            return {'items': [], 'next': None}

    controller = SpotifyController.__new__(SpotifyController)
    controller.spotipy_client = API()
    assert controller.handle_get({'type': 'artist_albums', 'value': 'spotify:artist:empty'}) == {'artist_albums': []}


def test_album_start_resolves_market_track_at_selected_position():
    from spotify_cmd_daemon.operations.start_playback import start_playback

    class API:
        def album(self, uri): return {}
        def album_tracks(self, uri, **kwargs):
            assert kwargs == {'limit': 1, 'offset': 2, 'market': 'from_token'}
            return {'items': [{'uri': 'spotify:track:playable'}]}
        def start_playback(self, **kwargs): self.arguments = kwargs

    api = API()
    start_playback(api, 'device', 'spotify:album:a', offset=2)
    assert api.arguments['offset'] == {'uri': 'spotify:track:playable'}
    assert api.arguments['position_ms'] == 0
    api.album_tracks = lambda *args, **kwargs: {'items': []}
    assert 'error' in start_playback(api, 'device', 'spotify:album:a')


def test_artists_tab_discards_late_album_result(monkeypatch):
    controller = TuiController()
    try:
        state = controller.state
        state.view = View.ARTISTS
        state.items = [{'spotify_id': 'a', 'name': 'Artist'}]
        loads = []
        monkeypatch.setattr(controller, 'start_load', lambda: loads.append((state.resource, state.resource_value)))
        controller.play_selected()
        token = controller._load_token
        controller.select_view(View.ALBUMS)
        controller.select_view(View.ARTISTS)
        assert loads[-1] == ('artists', None)
        controller._results.put(LoadResult(token, 'artist_albums', 'spotify:artist:a', None,
                                            {'artist_albums': [{'spotify_id': 'album'}]}))
        controller.tick()
        assert state.artist_context is None
        assert not state.items
    finally:
        controller.close()
