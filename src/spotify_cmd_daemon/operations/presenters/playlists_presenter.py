from .collection_presenter import CollectionPresenter

class PlaylistsPresenter(CollectionPresenter):
    def format(self):
        playlists = []

        for item in self.items:
            playlist_info = super().format_item(item)
            playlist_info.update({
                'owner': item['owner']['display_name'],
                'name': item['name']
            })
            playlists.append(playlist_info)
        return playlists
