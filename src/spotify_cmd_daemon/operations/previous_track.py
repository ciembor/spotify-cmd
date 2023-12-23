def previous_track(spotipy_client, device_id):
    response = spotipy_client.previous_track(device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": "Skipped to the previous track." }

    return response
