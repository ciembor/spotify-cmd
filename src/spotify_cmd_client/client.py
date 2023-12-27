import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
base_path = os.path.join(current_dir, "..", 'common')
sys.path.insert(0, base_path)

import socket
import json
from socket_message import SocketMessage
from socket_data_handler import SocketDataHandler
from config import Config

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
                if (format == 'verbose'):
                    formatted_response = json.dumps(response_dict, indent=2)
                    print(formatted_response)
                if (format == 'json'):
                    formatted_response = json.dumps(response_dict['payload'], indent=2)
                    print(formatted_response)
                else:
                    self.__print_output(response_dict['payload'])
        except socket.error as msg:
            print(f"Error receiving response from daemon: {msg}")

    def close(self):
        self.sock.close()

    def __print_output(self, data):
        if 'error' in data:
            print(f"Error: {data['error']}")
        elif 'notification' in data:
            print(data['notification'])
        elif 'albums' in data:
            self.__print_collection('albums', data['albums'])
        elif 'playlists' in data:
            self.__print_collection('playlists', data['playlists'])
        elif 'search_result' in data:
            self.print_search_result(data['search_result'])

    def __print_collection(self, type, items):
        print("──────────────────────────────────────────")
        for item in items:
            if (type=='albums'):
                self.__print_album(item)
            elif (type=='playlists'):
                self.__print_playlist(item)
            print("──────────────────────────────────────────")

    def __print_search_result(self, items):
        print("──────────────────────────────────────────")
        for item in items:
            print(f"URI: spotify:playlist:{item['spotify_id']}")
            print("──────────────────────────────────────────")

    def __print_album(self, album_data):
        print(f"Artist: {album_data['artists']}")
        print(f"Album: {album_data['name']}")
        print(f"URI: spotify:album:{album_data['spotify_id']}")

    def __print_playlist(self, playlist_data):
        print(f"Owner: {playlist_data['owner']}")
        print(f"Name: {playlist_data['name']}")
        print(f"URI: spotify:playlist:{playlist_data['spotify_id']}")
