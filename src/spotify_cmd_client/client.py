import socket
import json
from common.socket_message import SocketMessage
from common.socket_data_handler import SocketDataHandler
from common.config import Config
from .data_presenter import DataPresenter

class Client:
    def __init__(self):
        config = Config.get_instance()
        self.server_address = config.socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def connect(self):
        try:
            self.sock.connect(self.server_address)
        except socket.error as msg:
            print(f"Cannot connect to daemon: {msg}")
            return False
        return True

    def send_command(self, payload):
        try:
            socket_message = SocketMessage("request", payload)
            SocketDataHandler.send_data(self.sock, socket_message.to_json())
        except socket.error as msg:
            print(f"Error sending command to daemon: {msg}")

    def handle_response(self, format):
        try:
            response_json = SocketDataHandler.receive_data(self.sock)
            if response_json:
                response_dict = json.loads(response_json)
                if format == 'verbose':
                    formatted_response = json.dumps(response_dict, indent=2)
                    print(formatted_response)
                elif format == 'json':
                    formatted_response = json.dumps(response_dict['payload'], indent=2)
                    print(formatted_response)
                else:
                    DataPresenter.print_output(response_dict['payload'])
        except socket.error as msg:
            print(f"Error receiving response from daemon: {msg}")

    def close(self):
        self.sock.close()
