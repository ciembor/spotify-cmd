import json
import socket
import threading

from .config import Config
from .socket_data_handler import SocketDataHandler
from .socket_message import SocketMessage


class DaemonClient:
    """Transport client for one request or event subscription to the daemon."""

    def __init__(self):
        self.server_address = Config.get_instance().socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket_lock = threading.Lock()

    def connect(self):
        try:
            self.sock.connect(self.server_address)
        except socket.error:
            return False
        return True

    def close(self):
        with self._socket_lock:
            if self.sock.fileno() != -1:
                self.sock.close()

    def cancel(self):
        """Interrupt a pending request blocked while reading the daemon response."""
        with self._socket_lock:
            if self.sock.fileno() == -1:
                return
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()

    def request(self, payload):
        if self.sock.fileno() == -1:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if not self.connect():
            return {'error': 'Cannot connect to daemon.'}
        try:
            SocketDataHandler.send_data(self.sock, SocketMessage('request', payload).to_json())
            response = SocketDataHandler.receive_data(self.sock)
            return json.loads(response)['payload'] if response else {'error': 'No response from daemon.'}
        except (socket.error, json.JSONDecodeError) as error:
            return {'error': str(error)}
        finally:
            self.close()

    def subscribe(self, callback, stop_event=None):
        stop_event = stop_event or threading.Event()
        disconnected = False
        try:
            while not stop_event.is_set():
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                        connection.settimeout(1)
                        connection.connect(self.server_address)
                        SocketDataHandler.send_data(connection, SocketMessage('request', {'command': 'subscribe'}).to_json())
                        if disconnected:
                            callback({'event': 'connection_restored'})
                            disconnected = False
                        buffer = b''
                        while not stop_event.is_set():
                            try:
                                packet = connection.recv(SocketDataHandler.SOCKET_BUFFER_SIZE)
                            except socket.timeout:
                                continue
                            if not packet:
                                raise ConnectionError('Daemon connection closed')
                            buffer += packet
                            while SocketDataHandler.END_OF_MESSAGE in buffer:
                                response, buffer = buffer.split(SocketDataHandler.END_OF_MESSAGE, 1)
                                callback(json.loads(response.decode())['payload'])
                except (OSError, json.JSONDecodeError):
                    if not disconnected and not stop_event.is_set():
                        callback({'event': 'connection_error', 'error': 'Cannot connect to daemon.'})
                    disconnected = True
                    stop_event.wait(1)
        finally:
            self.close()
