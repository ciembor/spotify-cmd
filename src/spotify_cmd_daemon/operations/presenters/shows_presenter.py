from .collection_presenter import CollectionPresenter

class ShowsPresenter(CollectionPresenter):
    def format(self):
        shows = []

        for item in self.items:
            show_info = super().format_item(item)
            show_info.update({
                'name': item['name'],
                'description': item['description']
            })
            shows.append(show_info)
        return shows
