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
        config_file = self._find_config_file()
        if not config_file:
            raise Exception("Config file not found in any supported location.")

        self.config_path = config_file
        self.config_dir = os.path.dirname(config_file)

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

    def _find_config_file(self):
        explicit = os.environ.get("SPOTIFY_CMD_CONFIG")
        candidates = []
        if explicit:
            candidates.append(explicit)

        candidates.extend([
            os.path.expanduser('~/.config/spotify-cmd/config.ini'),
            '/var/lib/spotify-cmd/.config/spotify-cmd/config.ini',
            '/etc/spotify-cmd/config.ini',
        ])

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None
