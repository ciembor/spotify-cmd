from spotipy.exceptions import SpotifyException


def pause_playback(spotipy_client, device_id):
    current_playback = getattr(spotipy_client, 'current_playback', lambda: None)()
    if current_playback and current_playback.get('is_playing') is False:
        return {'notification': 'Playback already paused.'}
    try:
        response = spotipy_client.pause_playback(device_id=device_id)
    except SpotifyException as error:
        if error.http_status != 403:
            raise
        # Some Spotify Connect devices reject a request that explicitly names
        # their id while accepting the same command for the active device.
        response = spotipy_client.pause_playback()

    # Empty response == success.
    if not response:
        response = { "notification": "Playback paused." }

    return response
