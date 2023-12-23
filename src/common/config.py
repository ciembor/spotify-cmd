import os
import configparser

class Config:
    _instance = None

    @staticmethod
    def get_instance():
        if Config._instance is None:
            Config()
        return Config._instance

    def __init__(self):
        if Config._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Config._instance = self
            self.load_config()

    def load_config(self):
        config_dir = os.path.expanduser('~/.config/spotify-cmd')
        config_file = os.path.join(config_dir, 'config.ini')

        if not os.path.exists(config_file):
            raise Exception(f"Config file not found: {config_file}")

        config = configparser.ConfigParser()
        config.read(config_file)

        self.spotify_client_id = config.get('SPOTIFY', 'client_id', fallback=None)
        self.spotify_client_secret = config.get('SPOTIFY', 'client_secret', fallback=None)
        self.device_name = config.get('SPOTIFY', 'device_name', fallback=None)
        self.spotify_redirect_uri = config.get('SPOTIFY', 'redirect_uri', fallback='http://localhost:8888/callback')
        self.socket_path = config.get('SPOTIFY_CMD_DAEMON', 'socket_path', fallback='/tmp/spotify-cmd-daemon.sock')
        self.socket_buffer_size = config.getint('SPOTIFY_CMD_DAEMON', 'socket_buffer_size', fallback=1024)

        if not self.spotify_client_id or not self.spotify_client_secret:
            raise Exception("Spotify client_id and client_secret must be set in config.ini")
