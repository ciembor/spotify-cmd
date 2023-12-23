def pause_playback(spotipy_client, device_id):
    response = spotipy_client.pause_playback(device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": "Playback stopped." }

    return response
