from .presenters.tracks_presenter import TracksPresenter


def get_context_tracks(spotipy_client, resource_uri):
    resource_type, resource_id = resource_uri.split(':')[1:]
    tracks = []
    offset = 0
    while True:
        if resource_type == 'album':
            result = spotipy_client.album_tracks(resource_id, limit=50, offset=offset)
            items = result['items']
        elif resource_type == 'playlist':
            result = spotipy_client.playlist_items(resource_id, limit=100, offset=offset)
            items = [item['track'] for item in result['items'] if item.get('track')]
        else:
            raise ValueError(f'Unsupported track context: {resource_type}')
        tracks.extend(items)
        offset += len(result['items'])
        if not result.get('next'):
            break
    playback = spotipy_client.current_playback() or {}
    current = playback.get('item') or {}
    return {
        'tracks': TracksPresenter(tracks).format(),
        'playing_id': current.get('id'),
    }
