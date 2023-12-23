from .get_resource_from_library import get_resource_from_library

def get_album(spotipy_client, name):
    album = get_resource_from_library(lambda limit, offset: spotipy_client.current_user_saved_albums(limit=limit, offset=offset), name, is_album=True)

    if not album:
        raise Exception(f"Album '{name}' not found.")

    return album
