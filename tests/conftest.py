import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'src' / 'common')]

CONFIG_PATH = Path(tempfile.mkdtemp(prefix='spotify-cmd-tests-')) / 'config.ini'
CONFIG_PATH.write_text(
    '[SPOTIFY]\nclient_id = test-id\nclient_secret = test-secret\n'
    '[SPOTIFY_CMD_DAEMON]\nsocket_path = /tmp/spotify-cmd-test.sock\n'
)
os.environ['SPOTIFY_CMD_CONFIG'] = str(CONFIG_PATH)


def item(identifier, name='Name', **extra):
    value = {'id': identifier, 'name': name, 'uri': f'spotify:album:{identifier}'}
    value.update(extra)
    return value
