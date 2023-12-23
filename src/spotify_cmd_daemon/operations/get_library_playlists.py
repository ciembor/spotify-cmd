def get_library_playlists(spotipy_client):
    playlists = []
    limit = 50
    offset = 0

    while True:
        results = spotipy_client.current_user_playlists(limit=limit, offset=offset)
        for item in results['items']:
            playlist_info = {
                'spotify_id': item['id'],
                'type': 'playlist',
                'owner': item['owner']['display_name'],
                'name': item['name']
            }
            playlists.append(playlist_info)

        offset += limit
        if len(results['items']) < limit:
            break

    return { 'playlists': playlists }
