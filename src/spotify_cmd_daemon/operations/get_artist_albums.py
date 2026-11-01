from .presenters.albums_presenter import AlbumsPresenter


def get_artist_albums(spotipy_client, artist_uri):
    albums = []
    offset = 0
    while True:
        page = spotipy_client.artist_albums(
            artist_uri, album_type='album,single,compilation',
            country='from_token', limit=10, offset=offset,
        )
        albums.extend(AlbumsPresenter(page['items']).format())
        if not page.get('next'):
            return {'artist_albums': albums}
        offset += len(page['items'])
