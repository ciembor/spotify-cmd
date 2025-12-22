import signal
import sys
import argparse
import os
import daemon
from importlib.metadata import version, PackageNotFoundError
from .spotify_controller import SpotifyController
from .socket_server import SocketServer

lock_file = "/tmp/spotify-cmd-daemon.lock"

def signal_handler(sig, frame, server):
    server.stop_server()
    if os.path.exists(lock_file):
        os.remove(lock_file)
    sys.exit(0)

def get_pkg_version():
    try:
        return version("spotify-cmd")
    except PackageNotFoundError:
        return "unknown"

def create_server():
    spotify = SpotifyController()
    return SocketServer(spotify)

def install_signal_handlers(server):
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, server))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, server))

def ensure_lock():
    if os.path.exists(lock_file):
        print(f"Daemon already running ({lock_file} exists).")
        sys.exit(1)
    with open(lock_file, 'w'):
        pass

def run_server_foreground():
    ensure_lock()
    server = create_server()
    install_signal_handlers(server)
    server.start_server()

def run_server_daemon():
    with daemon.DaemonContext():
        ensure_lock()
        server = create_server()
        install_signal_handlers(server)
        server.start_server()

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--foreground", action="store_true", help="Run in foreground mode (not as a daemon)")
parser.add_argument("--version", action="store_true", help="Show spotify-cmd-daemon version and exit")
args = parser.parse_args()

if args.version:
    print(get_pkg_version())
    sys.exit(0)

if args.foreground:
    run_server_foreground()
else:
    run_server_daemon()
