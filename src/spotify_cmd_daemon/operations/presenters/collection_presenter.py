class CollectionPresenter:
    def __init__(self, items):
        self.items = items
        print(items)
    def format_item(self, item):
        return {
            'spotify_id': item['id'],
            'type': self.get_type()
        }

    def get_type(self):
        return self.__class__.__name__.replace('Presenter', '').lower()
