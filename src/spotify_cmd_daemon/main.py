import signal
import sys
import argparse
import os
import daemon
from .spotify_controller import SpotifyController
from .socket_server import SocketServer

def signal_handler(sig, frame, server):
    server.stop_server()
    if os.path.exists(lock_file):
        os.remove(lock_file)
    sys.exit(0)

def run_server(server):
    with daemon.DaemonContext():
        server.start_server()

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--foreground", action="store_true", help="Run in foreground mode (not as a daemon)")
args = parser.parse_args()

spotify = SpotifyController()
server = SocketServer(spotify)

lock_file = "/tmp/spotify-cmd-daemon.lock"
if os.path.exists(lock_file):
    print(f"Daemon already running ({lock_file} exists).")
    sys.exit(1)
else:
    with open(lock_file, 'w'): pass

signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, server))
signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, server))

if args.foreground:
    server.start_server()
else:
    run_server(server)
