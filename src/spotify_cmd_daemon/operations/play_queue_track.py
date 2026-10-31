def play_queue_track(spotipy_client, device_id, track_uri, artist_context_uri=None):
    playback = spotipy_client.current_playback() or {}
    if artist_context_uri:
        track = spotipy_client.track(track_uri)
        context_uri = track['album']['uri']
    else:
        context_uri = (playback.get('context') or {}).get('uri')
    if context_uri:
        spotipy_client.start_playback(
            context_uri=context_uri,
            offset={'uri': track_uri},
            device_id=device_id,
        )
    else:
        spotipy_client.start_playback(uris=[track_uri], device_id=device_id)
    return {'notification': 'Playback started.'}
