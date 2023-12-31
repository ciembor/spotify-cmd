from .presenters import *

def search(spotipy_client, search_query, resource_type):
    response = spotipy_client.search(q=search_query, type=resource_type)
    collection_key = next(iter(response.keys()))
    items = response[collection_key].get('items', [])
    result = None

    if resource_type == 'album':
        result = AlbumsPresenter(items).format()
    elif resource_type == 'artist':
        result = ArtistsPresenter(items).format()
    elif resource_type == 'playlist':
        result = PlaylistsPresenter(items).format()
    elif resource_type == 'track':
        result = TracksPresenter(items).format()
    elif resource_type == 'show':
        result = ShowsPresenter(items).format()
    elif resource_type == 'episode':
        result = EpisodesPresenter(items).format()

    return { f"{resource_type}s": result }
