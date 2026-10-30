from .presenters.tracks_presenter import TracksPresenter


def get_queue(spotipy_client):
    queue = spotipy_client.queue()
    current = queue.get('currently_playing')
    upcoming = queue.get('queue', [])
    tracks = []
    seen_ids = set()
    for track in ([current] if current else []) + upcoming:
        if track and track.get('id') not in seen_ids:
            tracks.append(track)
            seen_ids.add(track.get('id'))
    return {
        'tracks': TracksPresenter(tracks).format(),
        'playing_id': current.get('id') if current else None,
    }
