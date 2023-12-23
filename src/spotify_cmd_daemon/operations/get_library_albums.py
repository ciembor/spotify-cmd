def get_library_albums(spotipy_client):
    albums = []
    limit = 50
    offset = 0

    while True:
        results = spotipy_client.current_user_saved_albums(limit=limit, offset=offset)
        for item in results['items']:
            album = item['album']
            album_info = {
                'spotify_id': album['id'],
                'type': 'album',
                'artists': ', '.join([artist['name'] for artist in album['artists']]),
                'name': album['name']
            }
            albums.append(album_info)

        offset += limit
        if len(results['items']) < limit:
            break

    return { 'albums': albums }
