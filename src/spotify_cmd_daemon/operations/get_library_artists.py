from .presenters.artists_presenter import ArtistsPresenter


def get_library_artists(spotipy_client):
    artists = []
    after = None

    while True:
        response = spotipy_client.current_user_followed_artists(limit=50, after=after)
        page = response['artists']
        artists.extend(ArtistsPresenter(page['items']).format())
        after = (page.get('cursors') or {}).get('after')
        if not page.get('next') or not after:
            break

    return {'artists': artists}
