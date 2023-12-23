from .validators.validate_resource_uri import validate_resource_uri
from .helpers.check_resource_existence import check_resource_existence

def start_playback(spotipy_client, device_id, resource_uri, resource_name=None):
    response = None

    if validate_resource_uri(resource_uri):
        resource_type = resource_uri.split(':')[1]

        if not check_resource_existence(spotipy_client, resource_type, resource_uri):
            response = { "error": f"{resource_type.capitalize()} with uri {resource_uri} not found" }
        else:
            if (resource_type == 'track'):
                response = spotipy_client.start_playback(uris=[resource_uri], device_id=device_id)
            else:
                response = spotipy_client.start_playback(context_uri=resource_uri, device_id=device_id)
    else:
        raise Exception("Invalid resource uri.")

    # Empty response == success.
    if not response:
        if resource_name:
            response = { "notification": f"Playback of {resource_type} {resource_name} started."}
        else:
            response = { "notification": f"Playback of resource {resource_uri} started." }

    return response
