def resume_playback(spotipy_client, device_id):
    response = spotipy_client.start_playback(device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": "Playback resumed." }

    return response
