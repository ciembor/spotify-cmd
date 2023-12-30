from .presenters.albums_presenter import AlbumsPresenter

def get_library_albums(spotipy_client):
    albums = []
    limit = 50
    offset = 0

    while True:
        results = spotipy_client.current_user_saved_albums(limit=limit, offset=offset)
        raw_albums = list(map(lambda item: item['album'], results['items']))

        albums += AlbumsPresenter(raw_albums).format()

        offset += limit
        if len(results['items']) < limit:
            break

    return {'albums': albums}
