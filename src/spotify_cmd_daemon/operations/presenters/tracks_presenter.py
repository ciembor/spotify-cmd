from .collection_presenter import CollectionPresenter

class TracksPresenter(CollectionPresenter):
    def format(self):
        tracks = []

        for item in self.items:
            track_info = super().format_item(item)
            track_info.update({
                'artists': ', '.join([artist['name'] for artist in item['artists']]),
                'name': item['name'],
                'track_number': item.get('track_number'),
                'disc_number': item.get('disc_number'),
            })
            tracks.append(track_info)
        return tracks
