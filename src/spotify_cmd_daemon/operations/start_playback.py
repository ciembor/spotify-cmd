from .playlist_tracks import playlist_tracks
from .validators.validate_resource_uri import validate_resource_uri
from .helpers.check_resource_existence import check_resource_existence

def start_playback(spotipy_client, device_id, resource_uri, resource_name=None, offset=None):
    """Start a selected resource from the beginning, never its saved position."""
    response = None

    if validate_resource_uri(resource_uri):
        resource_type = resource_uri.split(':')[1]

        if not check_resource_existence(spotipy_client, resource_type, resource_uri):
            response = { "error": f"{resource_type.capitalize()} with uri {resource_uri} not found" }
        else:
            if (resource_type == 'track'):
                response = spotipy_client.start_playback(uris=[resource_uri], device_id=device_id, position_ms=0)
            else:
                if resource_type == 'playlist':
                    target = next((track for track in playlist_tracks(spotipy_client, resource_uri)
                                   if track['is_playable'] and (offset is None or track['context_position'] == offset)), None)
                    if target is None:
                        return {'error': 'No playable track at the requested playlist position.'}
                    # Starting a playlist must explicitly select its first
                    # playable item.  An explicit TUI selection, however,
                    # needs the entry position so duplicate track URIs remain
                    # distinguishable.
                    offset = ({'uri': target.get('uri') or f"spotify:track:{target['id']}"}
                              if offset is None else {'position': target['context_position']})
                arguments = {
                    'context_uri': resource_uri,
                    'device_id': device_id,
                    'position_ms': 0,
                }
                if resource_type == 'playlist':
                    arguments['offset'] = offset
                elif resource_type == 'album':
                    album_position = 0 if offset is None else offset
                    tracks = spotipy_client.album_tracks(
                        resource_uri, limit=1, offset=album_position, market='from_token',
                    )['items']
                    if not tracks:
                        return {'error': 'No track at the requested album position.'}
                    arguments['offset'] = ({'uri': tracks[0].get('uri') or f"spotify:track:{tracks[0]['id']}"}
                                           if offset is None else {'position': album_position})
                response = spotipy_client.start_playback(**arguments)
    else:
        raise Exception("Invalid resource uri.")

    # Empty response == success.
    if not response:
        if resource_name:
            response = { "notification": f"Playback of {resource_type} {resource_name} started."}
        else:
            response = { "notification": f"Playback of resource {resource_uri} started." }

    return response
