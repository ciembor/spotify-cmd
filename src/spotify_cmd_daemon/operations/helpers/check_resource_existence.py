from spotipy.exceptions import SpotifyException

def check_resource_existence(spotipy_client, resource_type, resource_uri):
    try:
        if resource_type == 'track':
            spotipy_client.track(resource_uri)
        elif resource_type == 'album':
            spotipy_client.album(resource_uri)
        elif resource_type == 'playlist':
            spotipy_client.playlist(resource_uri)
        else:
            return False
    except SpotifyException as e:
        if e.http_status == 404:
            return False
        else:
            raise

    return True
