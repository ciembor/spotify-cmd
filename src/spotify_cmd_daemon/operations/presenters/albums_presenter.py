from .collection_presenter import CollectionPresenter

class AlbumsPresenter(CollectionPresenter):
    def format(self):
        albums = []

        for item in self.items:
            album_info = super().format_item(item)
            album_info.update({
                'artists': ', '.join([artist['name'] for artist in item['artists']]),
                'name': item['name']
            })
            albums.append(album_info)
        return albums
