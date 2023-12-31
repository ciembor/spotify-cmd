class DataPresenter:
    PRINT_TEMPLATES = {
        'albums': [
            ('Artist', 'artists'),
            ('Album', 'name'),
            ('URI', lambda d: f"spotify:album:{d['spotify_id']}")
        ],
        'artists': [
            ('Artist', 'name'),
            ('Followers', 'followers'),
            ('URI', lambda d: f"spotify:artist:{d['spotify_id']}")
        ],
        'playlists': [
            ('Owner', 'owner'),
            ('Name', 'name'),
            ('URI', lambda d: f"spotify:playlist:{d['spotify_id']}")
        ],
        'tracks': [
            ('Artist', 'artists'),
            ('Name', 'name'),
            ('URI', lambda d: f"spotify:track:{d['spotify_id']}")
        ],
        'episodes': [
            ('Name', 'name'),
            ('Description', 'description'),
            ('URI', lambda d: f"spotify:episode:{d['spotify_id']}")
        ],
        'shows': [
            ('Name', 'name'),
            ('Description', 'description'),
            ('URI', lambda d: f"spotify:show:{d['spotify_id']}")
        ],
    }

    @staticmethod
    def print_output(data):
        if 'error' in data:
            print(f"Error: {data['error']}")
        elif 'notification' in data:
            print(data['notification'])
        else:
            for key, value in data.items():
                if key in DataPresenter.PRINT_TEMPLATES:
                    DataPresenter.__print_collection(key, value)
                    break

    @staticmethod
    def __print_collection(collection_type, items):
        horizontal_line = "─" * 50
        print(horizontal_line)
        for item in items:
            DataPresenter.__print_item(collection_type, item)
            print(horizontal_line)

    @staticmethod
    def __print_item(collection_type, item_data):
        for label, key in DataPresenter.PRINT_TEMPLATES[collection_type]:
            value = key(item_data) if callable(key) else item_data[key]
            print(f"{label}: {value}")
