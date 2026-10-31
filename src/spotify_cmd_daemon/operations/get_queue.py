from .presenters.tracks_presenter import TracksPresenter
from .get_context_tracks import get_context_tracks


def album_context_for_queue(spotipy_client, current, tracks):
    """Recognize a complete album queue rotated to the currently playing track."""
    album_uri = ((current or {}).get('album') or {}).get('uri')
    if not album_uri or len(tracks) < 2:
        return None
    try:
        album = get_context_tracks(spotipy_client, album_uri)
    except Exception:
        return None  # Queue browsing still works when album metadata is unavailable.
    if album['playback_context_uri'] not in (None, album_uri):
        return None
    queue_ids = [track.get('id') for track in tracks]
    album_ids = [track['spotify_id'] for track in album['tracks']]
    if len(queue_ids) != len(album_ids) or queue_ids[0] not in album_ids:
        return None
    offset = album_ids.index(queue_ids[0])
    if queue_ids != album_ids[offset:] + album_ids[:offset]:
        return None
    return {'uri': album_uri, 'name': album['context_name'], 'tracks': album['tracks']}


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
    response = {
        'tracks': TracksPresenter(tracks).format(),
        'playing_id': current.get('id') if current else None,
    }
    context = album_context_for_queue(spotipy_client, current, tracks)
    if context:
        response['context_uri'] = context['uri']
        response['context_name'] = context['name']
        response['context_tracks'] = context['tracks']
    return response
