import importlib

import pytest
from spotipy.exceptions import SpotifyException

from spotify_cmd_daemon import operations
from spotify_cmd_daemon.operations.helpers.check_resource_existence import check_resource_existence
from spotify_cmd_daemon.operations.helpers.get_resource_from_library import get_resource_from_library
from spotify_cmd_daemon.operations.helpers.get_resource_uri import get_resource_uri
from spotify_cmd_daemon.operations.presenters import (
    AlbumsPresenter, ArtistsPresenter, EpisodesPresenter, PlaylistsPresenter,
    ShowsPresenter, TracksPresenter,
)
from spotify_cmd_daemon.operations.validators.validate_resource_uri import validate_resource_uri
from spotify_cmd_daemon.operations.validators.validate_volume_percent import validate_volume_percent


class Spotify:
    def __init__(self):
        self.calls = []
        self.album_pages = []
        self.playlist_pages = []

    def _call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return None

    def start_playback(self, **kwargs): return self._call('start_playback', **kwargs)
    def pause_playback(self, **kwargs): return self._call('pause_playback', **kwargs)
    def seek_track(self, position_ms, **kwargs): return self._call('seek_track', position_ms=position_ms, **kwargs)
    def next_track(self, **kwargs): return self._call('next_track', **kwargs)
    def previous_track(self, **kwargs): return self._call('previous_track', **kwargs)
    def shuffle(self, **kwargs): return self._call('shuffle', **kwargs)
    def volume(self, **kwargs): return self._call('volume', **kwargs)
    def track(self, uri): return self._call('track', uri=uri)
    def album(self, uri): return self._call('album', uri=uri)
    def playlist(self, uri): return self._call('playlist', uri=uri)

    def current_user_saved_albums(self, limit, offset):
        return self.album_pages.pop(0)

    def current_user_playlists(self, limit, offset):
        return self.playlist_pages.pop(0)

    def current_playback(self):
        return {'item': {'id': 'playing'}}


def album(identifier='a', name='Album'):
    return {'id': identifier, 'name': name, 'uri': f'spotify:album:{identifier}', 'artists': [{'name': 'Artist'}]}


def playlist(identifier='p', name='Playlist'):
    return {'id': identifier, 'name': name, 'uri': f'spotify:playlist:{identifier}', 'owner': {'display_name': 'Owner'}}


def test_presenters_format_each_search_type():
    assert AlbumsPresenter([album()]).format()[0]['artists'] == 'Artist'
    assert ArtistsPresenter([{'id': 'a', 'name': 'Artist', 'followers': {'total': 7}}]).format()[0]['followers'] == 7
    assert PlaylistsPresenter([playlist()]).format()[0]['owner'] == 'Owner'
    assert TracksPresenter([{'id': 't', 'name': 'Track', 'artists': [{'name': 'Artist'}]}]).format()[0]['name'] == 'Track'
    assert EpisodesPresenter([{'id': 'e', 'name': 'Episode', 'description': 'Desc'}]).format()[0]['description'] == 'Desc'
    assert ShowsPresenter([{'id': 's', 'name': 'Show', 'description': 'Desc'}]).format()[0]['type'] == 'shows'


def test_library_operations_paginate_and_format():
    spotify = Spotify()
    spotify.album_pages = [{'items': [{'album': album()}] }]
    spotify.playlist_pages = [{'items': [playlist()]}]
    assert operations.get_library_albums(spotify)['albums'][0]['name'] == 'Album'
    assert operations.get_library_playlists(spotify)['playlists'][0]['name'] == 'Playlist'


def test_get_resource_from_library_paginates_and_finds_resources():
    pages = iter([{'items': [{'name': 'other'}] * 50}, {'items': [{'name': 'wanted'}]}])
    assert get_resource_from_library(lambda **kwargs: next(pages), 'wanted') == {'name': 'wanted'}
    assert get_resource_from_library(lambda **kwargs: {'items': []}, 'missing') is None


def test_resource_uri_uses_library_and_rejects_unknown(monkeypatch):
    module = importlib.import_module('spotify_cmd_daemon.operations.helpers.get_resource_uri')
    monkeypatch.setattr(module, 'get_album', lambda *_: album())
    monkeypatch.setattr(module, 'get_playlist', lambda *_: playlist())
    assert get_resource_uri(None, 'album', 'x') == 'spotify:album:a'
    assert get_resource_uri(None, 'playlist', 'x') == 'spotify:playlist:p'
    assert get_resource_uri(None, 'uri', 'spotify:track:t') == 'spotify:track:t'
    assert get_resource_uri(None, 'artist', 'x') is None


def test_playback_and_player_setting_operations():
    spotify = Spotify()
    assert operations.pause_playback(spotify, 'device')['notification'] == 'Playback paused.'
    assert operations.stop_playback(spotify, 'device')['notification'] == 'Playback stopped.'
    assert spotify.calls[-1] == ('seek_track', {'position_ms': 0, 'device_id': 'device'})
    assert operations.next_track(spotify, 'device')['notification'] == 'Skipped to the next track.'
    assert operations.previous_track(spotify, 'device')['notification'] == 'Skipped to the previous track.'
    assert operations.resume_playback(spotify, 'device')['notification'] == 'Playback resumed.'
    assert operations.set_shuffle(spotify, 'device', 'on')['notification'] == 'Shuffle is on.'
    assert operations.set_volume(spotify, 'device', 0)['notification'] == 'Volume set to 0%.'
    with pytest.raises(Exception, match='Shuffle'):
        operations.set_shuffle(spotify, 'device', 'yes')
    with pytest.raises(Exception, match='Volume'):
        operations.set_volume(spotify, 'device', 101)


def test_pause_retries_without_a_device_id_when_spotify_rejects_the_device():
    class Spotify:
        def __init__(self): self.calls = []

        def pause_playback(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise SpotifyException(403, -1, 'Restriction violated')

    spotify = Spotify()

    assert operations.pause_playback(spotify, 'device')['notification'] == 'Playback paused.'
    assert spotify.calls == [{'device_id': 'device'}, {}]


def test_pause_is_idempotent_when_playback_is_already_paused():
    class Spotify:
        def current_playback(self): return {'is_playing': False}
        def pause_playback(self, **_): raise AssertionError('must not call Spotify pause')

    assert operations.pause_playback(Spotify(), 'device') == {'notification': 'Playback already paused.'}


def test_stop_retries_seek_without_a_device_id_when_spotify_rejects_the_device():
    class Spotify:
        def current_playback(self): return {'is_playing': False}
        def pause_playback(self, **_): pass
        def seek_track(self, _position, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise SpotifyException(403, -1, 'Restriction violated')

        def __init__(self): self.calls = []

    spotify = Spotify()
    assert operations.stop_playback(spotify, 'device')['notification'] == 'Playback stopped.'
    assert spotify.calls == [{'device_id': 'device'}, {}]


def test_start_playback_validates_existence_and_selects_api(monkeypatch):
    spotify = Spotify()
    module = importlib.import_module('spotify_cmd_daemon.operations.start_playback')
    monkeypatch.setattr(module, 'check_resource_existence', lambda *_: True)
    assert operations.start_playback(spotify, 'd', 'spotify:track:t')['notification'].endswith('started.')
    assert spotify.calls[-1] == ('start_playback', {'uris': ['spotify:track:t'], 'device_id': 'd'})
    assert operations.start_playback(spotify, 'd', 'spotify:album:a', 'Name')['notification'] == 'Playback of album Name started.'
    operations.start_playback(spotify, 'd', 'spotify:playlist:p', offset=2)
    assert spotify.calls[-1] == ('start_playback', {
        'context_uri': 'spotify:playlist:p', 'device_id': 'd', 'offset': {'position': 2},
    })
    monkeypatch.setattr(module, 'check_resource_existence', lambda *_: False)
    assert 'not found' in operations.start_playback(spotify, 'd', 'spotify:album:a')['error']
    with pytest.raises(Exception, match='Invalid'):
        operations.start_playback(spotify, 'd', None)


def test_context_tracks_loads_album_and_playlist_pages():
    spotify = Spotify()
    track = {'id': 'track', 'name': 'Track', 'artists': [{'name': 'Artist'}]}
    spotify.album_tracks = lambda *_args, **_kwargs: {'items': [track], 'next': None}
    spotify.playlist_items = lambda *_args, **_kwargs: {'items': [{'track': track}, {'track': None}], 'next': None}

    assert operations.get_context_tracks(spotify, 'spotify:album:album-id')['tracks'][0]['name'] == 'Track'
    assert operations.get_context_tracks(spotify, 'spotify:playlist:playlist-id')['playing_id'] == 'playing'


def test_context_queue_and_queue_track_without_context_cover_real_playback_shapes():
    spotify = Spotify()
    track = {'id': 'track', 'name': 'Track', 'artists': [{'name': 'Artist'}]}
    spotify.queue = lambda: {'currently_playing': track, 'queue': [track, {'id': 'next', 'name': 'Next', 'artists': []}]}
    assert [item['spotify_id'] for item in operations.get_queue(spotify)['tracks']] == ['track', 'next']
    spotify.current_playback = lambda: {}
    operations.play_queue_track(spotify, 'device', 'spotify:track:next')
    assert spotify.calls[-1] == ('start_playback', {'uris': ['spotify:track:next'], 'device_id': 'device'})
    with pytest.raises(ValueError, match='Unsupported'):
        operations.get_context_tracks(spotify, 'spotify:artist:any')


def test_pause_and_stop_propagate_non_device_spotify_failures():
    class FailingSpotify:
        def current_playback(self): return {'is_playing': True}
        def pause_playback(self, **_): raise SpotifyException(401, -1, 'expired')
        def seek_track(self, *_args, **_kwargs): raise SpotifyException(401, -1, 'expired')

    with pytest.raises(SpotifyException):
        operations.pause_playback(FailingSpotify(), 'device')
    class SeekFailingSpotify:
        def current_playback(self): return {'is_playing': False}
        def seek_track(self, *_args, **_kwargs): raise SpotifyException(401, -1, 'expired')
    with pytest.raises(SpotifyException):
        operations.stop_playback(SeekFailingSpotify(), 'device')


def test_play_queue_track_uses_current_context_when_available():
    spotify = Spotify()
    spotify.current_playback = lambda: {'context': {'uri': 'spotify:album:album-id'}}

    assert operations.play_queue_track(spotify, 'device', 'spotify:track:track-id')['notification'] == 'Playback started.'
    assert spotify.calls[-1] == ('start_playback', {
        'context_uri': 'spotify:album:album-id',
        'offset': {'uri': 'spotify:track:track-id'},
        'device_id': 'device',
    })


def test_validators_and_existence_errors(monkeypatch):
    assert validate_resource_uri('spotify:track:abc123')
    assert not validate_resource_uri('spotify:show:abc')
    assert validate_volume_percent('100')
    assert not validate_volume_percent(-1)
    assert check_resource_existence(Spotify(), 'track', 'spotify:track:t')
    assert not check_resource_existence(Spotify(), 'show', 'spotify:show:s')


def test_search_formats_all_resource_types():
    class SearchSpotify:
        def search(self, q, type):
            data = {
                'album': [album()], 'artist': [{'id': 'a', 'name': 'A', 'followers': {'total': 1}}],
                'playlist': [playlist()], 'track': [{'id': 't', 'name': 'T', 'artists': []}],
                'show': [{'id': 's', 'name': 'S', 'description': 'D'}],
                'episode': [{'id': 'e', 'name': 'E', 'description': 'D'}],
            }
            return {f'{type}s': {'items': data[type]}}
    for kind in ('album', 'artist', 'playlist', 'track', 'show', 'episode'):
        assert operations.search(SearchSpotify(), 'query', kind)[f'{kind}s']
