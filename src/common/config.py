import os
import platform
import configparser

class Config:
    _instance = None

    @staticmethod
    def get_instance(require_credentials=True):
        if Config._instance is None:
            Config(require_credentials=require_credentials)
        if require_credentials:
            Config._instance.validate_credentials()
        return Config._instance

    def __init__(self, require_credentials=True):
        if Config._instance is not None:
            raise Exception("This class is a singleton!")
        self.load_config(require_credentials)
        Config._instance = self

    def load_config(self, require_credentials=True):
        config_file = self._find_config_file()
        if not config_file:
            raise ValueError("Config file not found in any supported location.")

        self.config_path = config_file
        self.config_dir = os.path.dirname(config_file)

        config = configparser.ConfigParser(interpolation=None)
        try:
            with open(config_file) as stream:
                config.read_file(stream)
        except PermissionError:
            # apt clients use the standard service socket without reading
            # the service user's private Spotify credentials.
            if require_credentials or config_file != '/var/lib/spotify-cmd/.config/spotify-cmd/config.ini':
                raise

        self.spotify_client_id = config.get('SPOTIFY', 'client_id', fallback=None)
        self.spotify_client_secret = config.get('SPOTIFY', 'client_secret', fallback=None)
        self.device_name = config.get('SPOTIFY', 'device_name', fallback=None)
        self.spotify_redirect_uri = config.get('SPOTIFY', 'redirect_uri', fallback='http://127.0.0.1:8888/callback')
        self.socket_path = config.get(
            'SPOTIFY_CMD_DAEMON',
            'socket_path',
            fallback=self._default_socket_path()
        )
        self.socket_buffer_size = config.getint('SPOTIFY_CMD_DAEMON', 'socket_buffer_size', fallback=1024)
        self.mpris_enabled = config.getboolean('SPOTIFY_CMD_DAEMON', 'mpris_enabled', fallback=False)
        self.mpris_bus_name = config.get('SPOTIFY_CMD_DAEMON', 'mpris_bus_name', fallback='org.mpris.MediaPlayer2.spotify_cmd')
        if self.socket_buffer_size <= 0:
            raise ValueError('socket_buffer_size must be positive')
        if not os.path.isabs(self.socket_path):
            raise ValueError('socket_path must be absolute')
        if require_credentials:
            self.validate_credentials()

    def validate_credentials(self):
        if not self.spotify_client_id or not self.spotify_client_secret:
            raise ValueError("Spotify client_id and client_secret must be set in config.ini")

    def _find_config_file(self):
        explicit = os.environ.get("SPOTIFY_CMD_CONFIG")
        candidates = []
        if explicit:
            return os.path.abspath(explicit) if os.path.exists(explicit) else None

        candidates.extend([
            os.path.expanduser('~/.config/spotify-cmd/config.ini'),
            '/var/lib/spotify-cmd/.config/spotify-cmd/config.ini',
            '/etc/spotify-cmd/config.ini',
        ])

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _default_socket_path(self):
        if platform.system().lower() == 'linux':
            return '/run/spotify-cmd/spotify-cmd.sock'
        return '/tmp/spotify-cmd-daemon.sock'
