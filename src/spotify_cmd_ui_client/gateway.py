from common.daemon_client import DaemonClient
import threading


class RequestCancellation:
    def __init__(self):
        self._cancelled = threading.Event()
        self._client = None
        self._lock = threading.Lock()

    @property
    def cancelled(self):
        return self._cancelled.is_set()

    def wait(self, timeout):
        return self._cancelled.wait(timeout)

    def attach(self, client):
        with self._lock:
            self._client = client
            if self.cancelled:
                client.cancel()

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            if self._client:
                self._client.cancel()


class SpotifyGateway:
    """Application-facing access to the daemon protocol."""

    def __init__(self, client_factory=DaemonClient):
        self.client_factory = client_factory

    def request(self, payload):
        return self.client_factory().request(payload)

    def load(self, resource, value, cancellation):
        client = self.client_factory()
        cancellation.attach(client)
        if cancellation.cancelled:
            return None
        response = client.request({'command': 'get', 'setting': None, 'type': resource, 'value': value})
        return None if cancellation.cancelled else response

    def play(self, resource_type, value):
        return self.request({'command': 'play', 'setting': None, 'type': resource_type, 'value': value})

    def command(self, command, setting=None, value=None):
        return self.request({'command': command, 'setting': setting, 'type': None, 'value': value})

    def subscribe(self, callback, stop_event=None):
        self.client_factory().subscribe(callback, stop_event)
