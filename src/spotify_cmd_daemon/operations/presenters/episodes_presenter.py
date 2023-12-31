from .collection_presenter import CollectionPresenter

class EpisodesPresenter(CollectionPresenter):
    def format(self):
        episodes = []

        for item in self.items:
            episode_info = super().format_item(item)
            episode_info.update({
                'name': item['name'],
                'description': item['description']
            })
            episodes.append(episode_info)
        return episodes
