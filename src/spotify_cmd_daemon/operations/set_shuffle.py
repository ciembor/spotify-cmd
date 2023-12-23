def set_shuffle(spotipy_client, device_id, shuffle_state):
    if shuffle_state not in ['on', 'off']:
        raise Exception("Shuffle state must be on or off.")
    boolean_shuffle_state = {'on': True, 'off': False}.get(shuffle_state)
    response = spotipy_client.shuffle(state=boolean_shuffle_state, device_id=device_id)

    # Empty response == success.
    if not response:
        response = { "notification": f"Shuffle is {shuffle_state}." }

    return response
