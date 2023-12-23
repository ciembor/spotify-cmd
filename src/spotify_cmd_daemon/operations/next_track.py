def next_track(spotipy_client, device_id):
    response = spotipy_client.next_track(device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": "Skipped to the next track." }

    return response
