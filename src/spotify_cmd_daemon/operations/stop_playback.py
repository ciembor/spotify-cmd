from .pause_playback import pause_playback
from spotipy.exceptions import SpotifyException


def stop_playback(spotipy_client, device_id):
    playback = spotipy_client.current_playback() or {}
    if not playback.get('item') or playback.get('is_playing') is False:
        return {'notification': 'Playback already stopped.'}
    pause_playback(spotipy_client, device_id)
    try:
        spotipy_client.seek_track(0, device_id=device_id)
    except SpotifyException as error:
        if error.http_status != 403:
            raise
        spotipy_client.seek_track(0)
    return {'notification': 'Playback stopped.'}
