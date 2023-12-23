import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
base_path = os.path.join(current_dir, "..", 'common')
sys.path.insert(0, base_path)

import socket
import json
from config import Config
from socket_message import SocketMessage
from socket_data_handler import SocketDataHandler

class SocketServer:
    config = Config.get_instance()
    SOCKET_BUFFER_SIZE = config.socket_buffer_size

    def __init__(self, spotify_controller):
        self.server_address = SocketServer.config.socket_path
        self.spotify_controller = spotify_controller
        self.sock = None

    def cleanup_socket(self):
        if os.path.exists(self.server_address):
            os.remove(self.server_address)

    def start_server(self):
        self.cleanup_socket()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(self.server_address)
            self.sock.listen(1)
        except socket.error as e:
            print(f"Cannot open socket: {e}")
            sys.exit(1)

        try:
            while True:
                connection, _ = self.sock.accept()
                with connection:
                    self.handle_connection(connection)
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.stop_server()

    def handle_connection(self, connection):
        try:
            data = SocketDataHandler.receive_data(connection)
            if data:
                socket_message = SocketMessage.from_json(data)
                self.spotify_controller.execute_command(socket_message)
                response = self.spotify_controller.get_response()
                SocketDataHandler.send_data(connection, response.to_json())
        except Exception as e:
            print(f"Connection error: {e}")

    def stop_server(self):
        if self.sock:
            self.sock.close()
            self.cleanup_socket()
