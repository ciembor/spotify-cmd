from .presenters.tracks_presenter import TracksPresenter
from .playlist_tracks import playlist_tracks


def get_context_tracks(spotipy_client, resource_uri):
    resource_type, resource_id = resource_uri.split(':')[1:]
    tracks = []
    offset = 0
    if resource_type == 'album':
        context_name = spotipy_client.album(resource_id)['name']
    elif resource_type == 'playlist':
        context_name = spotipy_client.playlist(resource_id, fields='name')['name']
    else:
        raise ValueError(f'Unsupported track context: {resource_type}')
    if resource_type == 'playlist':
        tracks = list(playlist_tracks(spotipy_client, resource_id))
    while resource_type == 'album':
        if resource_type == 'album':
            result = spotipy_client.album_tracks(resource_id, limit=50, offset=offset, market='from_token')
            items = result['items']
        tracks.extend(items)
        offset += len(result['items'])
        if not result.get('next'):
            break
    playback = spotipy_client.current_playback() or {}
    current = playback.get('item') or {}
    return {
        'tracks': TracksPresenter(tracks).format(),
        'playing_id': current.get('id'),
        'playing_track_number': current.get('track_number'),
        'playing_disc_number': current.get('disc_number'),
        'context_name': context_name,
        'playback_context_uri': (playback.get('context') or {}).get('uri'),
    }
