def search_spotify(spotipy_client, search_query, resource_type):
    response = spotipy_client.search(q=search_query, type=resource_type)

    return { 'search_result': response }
