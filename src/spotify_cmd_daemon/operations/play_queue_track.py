def play_queue_track(spotipy_client, device_id, track_uri, artist_context_uri=None, artist_tracks=()):
    if artist_context_uri:
        uris = [f"spotify:track:{track['spotify_id']}" for track in artist_tracks]
        if track_uri not in uris:
            return {'error': 'Selected track is no longer in the artist queue.'}
        track = spotipy_client.track(track_uri, market='from_token')
        album_uri = (track.get('album') or {}).get('uri')
        if not album_uri or track.get('is_playable') is False:
            return {'error': 'Selected track is unavailable for playback.'}
        spotipy_client.start_playback(
            context_uri=album_uri, offset={'uri': track.get('uri') or track_uri},
            device_id=device_id, position_ms=0,
        )
        return {'notification': 'Playback started from the track album.'}
    playback = spotipy_client.current_playback() or {}
    context_uri = (playback.get('context') or {}).get('uri')
    if (context_uri or '').startswith(('spotify:album:', 'spotify:playlist:')):
        spotipy_client.start_playback(
            context_uri=context_uri, offset={'uri': track_uri},
            device_id=device_id, position_ms=0,
        )
    else:
        spotipy_client.start_playback(uris=[track_uri], device_id=device_id, position_ms=0)
    return {'notification': 'Playback started.'}
