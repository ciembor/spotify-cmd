def get_resource_from_library(fetcher, resource_name, is_album=False):
    items = []
    offset = 0
    limit = 50

    while True:
        results = fetcher(limit=limit, offset=offset)
        fetched_items = results['items']
        if is_album:
            fetched_items = [item['album'] for item in fetched_items]
        items.extend(fetched_items)

        if len(results['items']) < limit:
            break
        offset += limit

    resource = next((item for item in items if item['name'] == resource_name), None)
    return resource
