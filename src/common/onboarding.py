"""Explicit setup and first-run guidance, without import-time configuration."""

import configparser
import os
from pathlib import Path

from .config import Config


SERVICE_CONFIG = '/var/lib/spotify-cmd/.config/spotify-cmd/config.ini'
SCOPE = 'user-library-read,user-follow-read,user-read-playback-state,user-modify-playback-state,playlist-read-private'


def initialize(service=False):
    existing = Config.__new__(Config)._find_config_file()
    path = Path(SERVICE_CONFIG if service else (os.environ.get('SPOTIFY_CMD_CONFIG') or existing
                or os.path.expanduser('~/.config/spotify-cmd/config.ini'))).absolute()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    socket_path = '/run/spotify-cmd/spotify-cmd.sock' if service else f'/tmp/spotify-cmd-{os.getuid()}.sock'
    template = f'''# Create an app at https://developer.spotify.com/dashboard
# Register this exact redirect URI in the app settings.
[SPOTIFY]
client_id =
client_secret =
redirect_uri = http://127.0.0.1:8888/callback
# Optional: exact Spotify Connect name (official Spotify app or spotifyd).
# device_name = My device

[SPOTIFY_CMD_DAEMON]
socket_path = {socket_path}
socket_buffer_size = 1024
mpris_enabled = false
'''
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f'Configuration already exists; kept unchanged: {path}')
    else:
        with os.fdopen(fd, 'w') as stream:
            stream.write(template)
        print(f'Created configuration: {path}')
    print('Fill in client_id and client_secret, then run spotify-cmd config check and spotify-cmd auth.')
    return path


def prepare(require_credentials=False):
    """Fail before curses or daemonization, with actionable local diagnostics."""
    try:
        if not Config.__new__(Config)._find_config_file():
            path = initialize()
            raise ValueError(f'Edit {path}, then run spotify-cmd config check and spotify-cmd auth.')
        return Config.get_instance(require_credentials=require_credentials)
    except (OSError, ValueError, configparser.Error) as error:
        raise SystemExit(f'Configuration error: {error}') from error


def authenticate(no_browser=False):
    from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler

    config = prepare(require_credentials=True)
    cache_dir = Path(config.config_dir) / 'cache'
    cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache_path = cache_dir / 'token-cache'
    # The library creates the cache; keep tokens private even under a loose umask.
    old_umask = os.umask(0o077)
    try:
        if cache_path.exists():
            cache_path.chmod(0o600)
        oauth = SpotifyOAuth(
            client_id=config.spotify_client_id, client_secret=config.spotify_client_secret,
            redirect_uri=config.spotify_redirect_uri, scope=SCOPE,
            cache_handler=CacheFileHandler(cache_path=str(cache_path), username='spotify-cmd'),
            open_browser=not no_browser,
        )
        oauth.get_access_token(as_dict=False)
    finally:
        os.umask(old_umask)
    print('Authorization complete. Start spotify-cmd-daemon (or restart the spotify-cmd systemd service).')
