import os
import sys
import socket
import json
import threading
import time
from common.config import Config
from common.socket_message import SocketMessage
from common.socket_data_handler import SocketDataHandler

class SocketServer:
    config = Config.get_instance()
    SOCKET_BUFFER_SIZE = config.socket_buffer_size
    SEEK_CONFIRMATION_TOLERANCE_MS = 1_500
    SEEK_CONFIRMATION_TIMEOUT_SECONDS = 5

    def __init__(self, spotify_controller):
        self.server_address = SocketServer.config.socket_path
        self.spotify_controller = spotify_controller
        self.sock = None
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
        while self.sock:
            try:
                state = self.spotify_controller.get_playback_state()
                if self.should_defer_seek_state(state):
                    time.sleep(1)
                    continue
                if self.event_state(state) != self.event_state(self.last_state or {}):
                    self.publish_state(state)
            except Exception as error:
                print(f"Playback state error: {error}")
            time.sleep(1)

    def cleanup_socket(self):
        if os.path.exists(self.server_address):
            try:
                os.remove(self.server_address)
            except FileNotFoundError:
                pass

    def start_server(self):
        self.cleanup_socket()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(self.server_address)
            self.sock.listen(socket.SOMAXCONN)
        except socket.error as e:
            print(f"Cannot open socket: {e}")
            sys.exit(1)

        try:
            threading.Thread(target=self.poll_state, daemon=True).start()
            while True:
                connection, _ = self.sock.accept()
                threading.Thread(target=self.handle_connection, args=(connection,), daemon=True).start()
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.stop_server()

    def handle_connection(self, connection):
        try:
            data = SocketDataHandler.receive_data(connection)
            if data:
                socket_message = SocketMessage.from_json(data)
                if socket_message.payload.get('command') == 'subscribe':
                    with self.subscribers_lock:
                        self.subscribers.add(connection)
                    self.publish_state(force=True)
                    return
                response = self.spotify_controller.execute_command(socket_message)
                command = socket_message.payload.get('command')
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
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            if connection not in self.subscribers:
                close = getattr(connection, 'close', None)
                if close:
                    close()

    def stop_server(self):
        if self.sock:
            self.sock.close()
            self.cleanup_socket()
        with self.subscribers_lock:
            for connection in self.subscribers:
                connection.close()
            self.subscribers.clear()
