import os
import socket
import logging
import threading
import time

from common.config import Config
from common.protocol import CommandRequest, ProtocolError
from common.socket_message import SocketMessage
from common.socket_data_handler import SocketDataHandler


logger = logging.getLogger(__name__)


class SocketServer:
    SEEK_CONFIRMATION_TOLERANCE_MS = 1_500
    SEEK_CONFIRMATION_TIMEOUT_SECONDS = 5
    POLL_INTERVAL_SECONDS = 1

    def __init__(self, spotify_controller, config=None):
        self.config = config or Config.get_instance()
        self.server_address = self.config.socket_path
        self.spotify_controller = spotify_controller
        self.sock = None
        self._stop_event = threading.Event()
        self._poll_thread = None
        self.subscribers = set()
        self.subscribers_lock = threading.Lock()
        self.publish_lock = threading.Lock()
        self.last_state = None
        self.state_revision = 0
        self.seek_lock = threading.Lock()
        self.pending_seek_target = None
        self.pending_seek_deadline = None

    def current_state_revision(self):
        with self.publish_lock:
            return self.state_revision

    def defer_stale_seek_states(self, target_ms):
        with self.seek_lock:
            self.pending_seek_target = target_ms
            self.pending_seek_deadline = time.monotonic() + self.SEEK_CONFIRMATION_TIMEOUT_SECONDS

    def should_defer_seek_state(self, state):
        with self.seek_lock:
            if self.pending_seek_target is None:
                return False
            progress_ms = state.get('progress_ms')
            if progress_ms is not None and abs(progress_ms - self.pending_seek_target) <= self.SEEK_CONFIRMATION_TOLERANCE_MS:
                self.pending_seek_target = None
                self.pending_seek_deadline = None
                return False
            if time.monotonic() >= self.pending_seek_deadline:
                self.pending_seek_target = None
                self.pending_seek_deadline = None
                return False
            return True

    @staticmethod
    def event_state(state):
        """Return the state fields that require clients to refresh their views."""
        return {
            'is_playing': state.get('is_playing'),
            'shuffle_state': state.get('shuffle_state'),
            'volume_percent': state.get('volume_percent'),
            'progress_ms': state.get('progress_ms'),
            'item_id': state.get('item', {}).get('id'),
            'context_uri': (state.get('display_context') or state.get('context') or {}).get('uri'),
        }

    def publish_state(self, state=None, force=False):
        # A Unix socket is a byte stream. Keep every event write atomic relative
        # to other publishers so two JSON documents can never interleave.
        with self.publish_lock:
            state = state or self.spotify_controller.get_playback_state()
            if not force and self.event_state(state) == self.event_state(self.last_state or {}):
                return
            self.state_revision += 1
            encoded = SocketMessage(
                'event', {'event': 'state_changed', 'state': state}, state_revision=self.state_revision,
            ).to_json()
            with self.subscribers_lock:
                subscribers = list(self.subscribers)
            for connection in subscribers:
                try:
                    SocketDataHandler.send_data(connection, encoded)
                except OSError:
                    with self.subscribers_lock:
                        self.subscribers.discard(connection)
            self.last_state = state

    def poll_state(self):
        while self.sock and not self._stop_event.is_set():
            try:
                state = self.spotify_controller.get_playback_state()
                if self.should_defer_seek_state(state):
                    time.sleep(1)
                    continue
                if self.event_state(state) != self.event_state(self.last_state or {}):
                    self.publish_state(state)
            except Exception as error:
                logger.warning('Playback state error: %s', error)
            self._stop_event.wait(self.POLL_INTERVAL_SECONDS)

    def cleanup_socket(self):
        if os.path.exists(self.server_address):
            try:
                os.remove(self.server_address)
            except FileNotFoundError:
                pass

    def start_server(self):
        self._stop_event.clear()
        self.cleanup_socket()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(self.server_address)
            self.sock.listen(socket.SOMAXCONN)
        except socket.error as e:
            self.stop_server()
            raise RuntimeError(f'Cannot open socket: {e}') from e

        try:
            self._poll_thread = threading.Thread(target=self.poll_state, name='spotify-cmd-poller', daemon=True)
            self._poll_thread.start()
            while not self._stop_event.is_set():
                try:
                    connection, _ = self.sock.accept()
                except OSError:
                    if self._stop_event.is_set():
                        break
                    raise
                threading.Thread(target=self.handle_connection, args=(connection,), daemon=True).start()
        except OSError as error:
            logger.error('Server error: %s', error)
        finally:
            self.stop_server()

    def handle_connection(self, connection):
        try:
            data = SocketDataHandler.receive_data(connection)
            if data:
                socket_message = SocketMessage.from_json(data)
                request = CommandRequest.from_payload(socket_message.payload)
                if request.command == 'subscribe':
                    with self.subscribers_lock:
                        self.subscribers.add(connection)
                    self.publish_state(force=True)
                    return
                response = self.spotify_controller.execute_command(socket_message)
                command = request.command
                if command == 'seek' and 'error' not in response and response.get('progress_ms') is not None:
                    self.defer_stale_seek_states(response['progress_ms'])
                SocketDataHandler.send_data(
                    connection,
                    SocketMessage('response', response, state_revision=self.current_state_revision()).to_json(),
                )
                # Spotify updates its playback state asynchronously.  Publishing
                # immediately after play can therefore broadcast the old track
                # and clear the TUI selection before the poller sees the new one.
                # The regular poll publishes the authoritative state shortly
                # afterwards.
                if command not in ('play', 'seek'):
                    self.publish_state()
        except ProtocolError as error:
            SocketDataHandler.send_data(connection, SocketMessage('response', {'error': str(error)}).to_json())
        except Exception as error:
            logger.warning('Connection error: %s', error)
        finally:
            if connection not in self.subscribers:
                close = getattr(connection, 'close', None)
                if close:
                    close()

    def stop_server(self):
        self._stop_event.set()
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.close()
            except OSError:
                pass
            self.cleanup_socket()
        with self.subscribers_lock:
            subscribers, self.subscribers = list(self.subscribers), set()
        for connection in subscribers:
            try:
                connection.close()
            except OSError:
                pass
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join(timeout=self.POLL_INTERVAL_SECONDS + 0.1)
            self._poll_thread = None
