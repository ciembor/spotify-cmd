"""Playlist entries with their original Spotify context positions."""


def playlist_tracks(client, playlist_id):
    offset = 0
    while True:
        page = client.playlist_items(playlist_id, limit=100, offset=offset, market='from_token')
        for index, entry in enumerate(page['items']):
            track = entry.get('track')
            if not track:
                track = {'id': None, 'name': 'Unavailable track', 'artists': [], 'is_playable': False}
            playable = bool(track.get('id') and not track.get('is_local')
                            and track.get('is_playable') is not False and not track.get('restrictions'))
            yield {**track, 'context_position': offset + index, 'is_playable': playable}
        offset += len(page['items'])
        if not page.get('next'):
            return
