from .presenters.playlists_presenter import PlaylistsPresenter

def get_library_playlists(spotipy_client):
    playlists = []
    limit = 50
    offset = 0

    while True:
        results = spotipy_client.current_user_playlists(limit=limit, offset=offset)
        playlists += PlaylistsPresenter(results['items']).format()

        offset += limit
        if len(results['items']) < limit:
            break

    return {'playlists': playlists}
