from .get_resource_from_library import get_resource_from_library

def get_playlist(spotipy_client, name):
    playlist = get_resource_from_library(spotipy_client.current_user_playlists, name)

    if not playlist:
        raise Exception(f"Playlist '{name}' not found.")

    return playlist
