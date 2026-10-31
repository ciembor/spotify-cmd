def get_artist(spotipy_client, name):
    after = None

    while True:
        response = spotipy_client.current_user_followed_artists(limit=50, after=after)
        page = response['artists']
        artist = next((item for item in page['items'] if item['name'] == name), None)
        if artist:
            return artist
        after = (page.get('cursors') or {}).get('after')
        if not page.get('next') or not after:
            break

    raise Exception(f"Artist '{name}' not found among followed artists.")
