from .get_album import get_album
from .get_playlist import get_playlist

def get_resource_uri(spotipy_client, type, value):
    resource_uri = None

    if (type == 'album'):
        resource_uri = get_album(spotipy_client, value)['uri']
    elif (type == 'playlist'):
        resource_uri = get_playlist(spotipy_client, value)['uri']
    elif (type == 'uri'):
        resource_uri = value

    return resource_uri
