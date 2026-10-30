import importlib

import pytest

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
    assert operations.pause_playback(spotify, 'device')['notification'] == 'Playback stopped.'
    assert operations.next_track(spotify, 'device')['notification'] == 'Skipped to the next track.'
    assert operations.previous_track(spotify, 'device')['notification'] == 'Skipped to the previous track.'
    assert operations.resume_playback(spotify, 'device')['notification'] == 'Playback resumed.'
    assert operations.set_shuffle(spotify, 'device', 'on')['notification'] == 'Shuffle is on.'
    assert operations.set_volume(spotify, 'device', 0)['notification'] == 'Volume set to 0%.'
    with pytest.raises(Exception, match='Shuffle'):
        operations.set_shuffle(spotify, 'device', 'yes')
    with pytest.raises(Exception, match='Volume'):
        operations.set_volume(spotify, 'device', 101)


def test_start_playback_validates_existence_and_selects_api(monkeypatch):
    spotify = Spotify()
    module = importlib.import_module('spotify_cmd_daemon.operations.start_playback')
    monkeypatch.setattr(module, 'check_resource_existence', lambda *_: True)
    assert operations.start_playback(spotify, 'd', 'spotify:track:t')['notification'].endswith('started.')
    assert spotify.calls[-1] == ('start_playback', {'uris': ['spotify:track:t'], 'device_id': 'd'})
    assert operations.start_playback(spotify, 'd', 'spotify:album:a', 'Name')['notification'] == 'Playback of album Name started.'
    monkeypatch.setattr(module, 'check_resource_existence', lambda *_: False)
    assert 'not found' in operations.start_playback(spotify, 'd', 'spotify:album:a')['error']
    with pytest.raises(Exception, match='Invalid'):
        operations.start_playback(spotify, 'd', None)


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
