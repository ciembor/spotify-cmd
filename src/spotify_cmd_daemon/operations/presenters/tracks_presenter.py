from .collection_presenter import CollectionPresenter

class TracksPresenter(CollectionPresenter):
    def format(self):
        tracks = []

        for item in self.items:
            track_info = super().format_item(item)
            track_info.update({
                'artists': ', '.join([artist['name'] for artist in item['artists']]),
                'name': item['name']
            })
            tracks.append(track_info)
        return tracks
