"""Daemon-owned context for playback that Spotify's API does not retain."""

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class ArtistQueue:
    uri: str
    name: str
    tracks: tuple = ()
    pending: bool = True


class PlaybackSession:
    """Thread-safe state shared by concurrent daemon requests.

    Spotify can omit an artist context after a track from that artist is chosen.
    The daemon therefore retains the artist queue for the lifetime of its
    playback session. Network calls are deliberately made outside this lock.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._artist_queue = None

    def begin_artist_queue(self, uri, name):
        with self._lock:
            self._artist_queue = ArtistQueue(uri, name or 'Now playing')
            return self._artist_queue

    def artist_queue(self):
        with self._lock:
            return self._artist_queue

    def complete_artist_queue(self, queue, tracks):
        with self._lock:
            if self._artist_queue != queue:
                return None
            self._artist_queue = ArtistQueue(queue.uri, queue.name, tuple(tracks), pending=False)
            return self._artist_queue

    def clear_artist_queue(self, queue=None):
        with self._lock:
            if queue is None or self._artist_queue == queue:
                self._artist_queue = None
