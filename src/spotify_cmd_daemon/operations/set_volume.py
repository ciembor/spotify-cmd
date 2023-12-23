from .validators.validate_volume_percent import validate_volume_percent

def set_volume(spotipy_client, device_id, volume_percent):
    if not validate_volume_percent(volume_percent):
        raise Exception("Volume must be integer between 0 and 100.")
    response = spotipy_client.volume(volume_percent=volume_percent, device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": f"Volume set to {volume_percent}%." }

    return response
