from .collection_presenter import CollectionPresenter

class ArtistsPresenter(CollectionPresenter):
    def format(self):
        artists = []

        for item in self.items:
            artist_info = super().format_item(item)
            artist_info.update({
                'name': item['name'],
                'followers': item['followers']['total']
            })
            artists.append(artist_info)
        return artists
