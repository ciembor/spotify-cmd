import signal
import sys
import argparse
import os
import daemon
from importlib.metadata import version, PackageNotFoundError
from .spotify_controller import SpotifyController
from .socket_server import SocketServer
from .mpris import MprisService
from common.onboarding import prepare

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

def _pid_is_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

def ensure_lock():
    if os.path.exists(lock_file):
        try:
            content = open(lock_file, 'r').read().strip()
            pid = int(content) if content else None
        except (OSError, ValueError):
            pid = None

        if pid and _pid_is_running(pid):
            print(f"Daemon already running (pid {pid}, {lock_file} exists).")
            sys.exit(1)

        try:
            os.remove(lock_file)
        except OSError:
            pass

    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))

def run_server_foreground():
    ensure_lock()
    server = create_server()
    controller = getattr(server, 'spotify_controller', None)
    if controller and controller.config.mpris_enabled:
        MprisService(controller, controller.config.mpris_bus_name).start()
    install_signal_handlers(server)
    server.start_server()

def run_server_daemon():
    with daemon.DaemonContext():
        ensure_lock()
        server = create_server()
        install_signal_handlers(server)
        server.start_server()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--foreground", action="store_true", help="Run in foreground mode (not as a daemon)")
    parser.add_argument("--version", action="store_true", help="Show spotify-cmd-daemon version and exit")
    args = parser.parse_args()

    if args.version:
        print(get_pkg_version())
        return

    prepare(require_credentials=True)
    if args.foreground:
        run_server_foreground()
    else:
        run_server_daemon()


if __name__ == "__main__":  # pragma: no cover - exercised by console entry point
    main()
