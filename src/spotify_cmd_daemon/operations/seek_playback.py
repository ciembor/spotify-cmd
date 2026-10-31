def seek_playback(spotipy_client, device_id, position_ms):
    """Move to an absolute position without a preliminary Spotify API read."""
    try:
        target_ms = max(int(position_ms), 0)
    except (TypeError, ValueError):
        return {'error': 'Seek position must be a non-negative integer.'}

    response = spotipy_client.seek_track(target_ms, device_id=device_id)
    if not response:
        response = {'notification': f'Seeked to {target_ms // 1000}s.'}
    return {**response, 'progress_ms': target_ms}
