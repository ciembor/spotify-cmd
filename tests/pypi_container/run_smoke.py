"""Black-box check for the package installed from PyPI inside this container."""
import json
import os
import socket
import subprocess
import tempfile
import threading
from importlib.metadata import version
from pathlib import Path


END_OF_MESSAGE = b'<END_OF_MESSAGE>'
PACKAGE_VERSION = os.environ['PACKAGE_VERSION']


def command(*args, env=None):
    result = subprocess.run(args, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def serve_once(socket_path, received):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(socket_path)
        server.listen(1)
        connection, _ = server.accept()
        with connection:
            message = b''
            while END_OF_MESSAGE not in message:
                packet = connection.recv(1024)
                assert packet, 'client closed its request before the terminator'
                message += packet
            received.append(json.loads(message.replace(END_OF_MESSAGE, b'').decode()))
            response = {
                'message_type': 'response', 'message_id': 'container-smoke-test',
                'timestamp': '2026-10-30T00:00:00',
                'payload': {'notification': 'Playback paused by test server.'},
                'app_id': 'test-server',
            }
            connection.sendall(json.dumps(response).encode() + END_OF_MESSAGE)


assert version('spotify-cmd') == PACKAGE_VERSION
assert command('spotify-cmd', 'version').strip() == PACKAGE_VERSION
assert command('spotify-cmd-daemon', '--version').strip() == PACKAGE_VERSION
assert 'usage:' in command('spotify-cmd', '--help').lower()
assert 'usage:' in command('spotify-cmd-daemon', '--help').lower()

with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    socket_path = directory / 'daemon.sock'
    config_path = directory / 'config.ini'
    config_path.write_text(
        '[SPOTIFY]\nclient_id = test-client\nclient_secret = test-secret\n'
        f'[SPOTIFY_CMD_DAEMON]\nsocket_path = {socket_path}\n'
    )
    received = []
    server = threading.Thread(target=serve_once, args=(str(socket_path), received))
    server.start()
    while not socket_path.exists():
        pass
    output = command('spotify-cmd', 'pause', env=os.environ | {'SPOTIFY_CMD_CONFIG': str(config_path)})
    server.join(timeout=5)
    assert not server.is_alive(), 'server did not receive a client request'
    assert received[0]['message_type'] == 'request'
    assert received[0]['payload'] == {'command': 'pause', 'setting': None, 'type': None, 'value': None}
    assert output == 'Playback paused by test server.\n'
