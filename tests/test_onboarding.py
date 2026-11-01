import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from common.config import Config
from common import onboarding
from spotify_cmd_client import main as cli
from spotify_cmd_daemon import main as daemon
from spotify_cmd_ui_client import main as ui


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / 'settings' / 'config.ini'
    monkeypatch.setenv('SPOTIFY_CMD_CONFIG', str(path))
    monkeypatch.setattr(Config, '_instance', None)
    return path


def test_init_is_private_and_never_overwrites(config_path, capsys):
    onboarding.initialize()
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700
    text = config_path.read_text()
    assert '127.0.0.1' in text
    assert f'/tmp/spotify-cmd-{os.getuid()}.sock' in text
    config_path.write_text('existing secret configuration')
    onboarding.initialize()
    assert config_path.read_text() == 'existing secret configuration'
    assert 'existing secret' not in capsys.readouterr().out


def test_service_template_and_user_default(tmp_path, monkeypatch):
    monkeypatch.delenv('SPOTIFY_CMD_CONFIG', raising=False)
    monkeypatch.setattr(Config, '_find_config_file', lambda self: None)
    monkeypatch.setattr(os.path, 'expanduser', lambda _: str(tmp_path / 'user.ini'))
    assert onboarding.initialize() == tmp_path / 'user.ini'
    monkeypatch.setattr(onboarding, 'SERVICE_CONFIG', str(tmp_path / 'service.ini'))
    path = onboarding.initialize(service=True)
    assert '/run/spotify-cmd/spotify-cmd.sock' in path.read_text()


@pytest.mark.parametrize('entry', ['cli', 'ui', 'daemon'])
def test_first_launch_creates_config_before_runtime(config_path, monkeypatch, entry):
    monkeypatch.setattr(sys, 'argv', ['spotify-cmd', 'pause'] if entry == 'cli' else ['app'])
    monkeypatch.setattr(ui.curses, 'wrapper', lambda *_: pytest.fail('curses started'))
    monkeypatch.setattr(daemon, 'run_server_daemon', lambda: pytest.fail('daemon started'))
    with pytest.raises(SystemExit, match='Edit .*config.ini'):
        {'cli': cli.main, 'ui': ui.main, 'daemon': daemon.main}[entry]()
    assert config_path.exists()


def test_transport_config_does_not_require_secrets(config_path):
    onboarding.initialize()
    config = onboarding.prepare()
    assert not config.spotify_client_secret
    with pytest.raises(SystemExit, match='client_id and client_secret'):
        onboarding.prepare(require_credentials=True)


def test_apt_clients_can_use_private_service_config(monkeypatch):
    monkeypatch.setattr(Config, '_instance', None)
    monkeypatch.setattr(Config, '_find_config_file', lambda self: onboarding.SERVICE_CONFIG)
    monkeypatch.setattr('builtins.open', lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr('platform.system', lambda: 'Linux')
    assert onboarding.prepare().socket_path == '/run/spotify-cmd/spotify-cmd.sock'
    monkeypatch.setattr(Config, '_instance', None)
    with pytest.raises(SystemExit, match='Configuration error'):
        onboarding.prepare(require_credentials=True)


@pytest.mark.parametrize('body, message', [
    ('invalid ini', 'Configuration error'),
    ('[SPOTIFY_CMD_DAEMON]\nsocket_buffer_size = 0', 'must be positive'),
    ('[SPOTIFY_CMD_DAEMON]\nsocket_path = relative', 'must be absolute'),
    ('[SPOTIFY_CMD_DAEMON]\nmpris_enabled = maybe', 'Not a boolean'),
])
def test_bad_config_is_reported_before_daemonization(config_path, monkeypatch, body, message):
    config_path.parent.mkdir()
    config_path.write_text(body)
    monkeypatch.setattr(sys, 'argv', ['daemon'])
    monkeypatch.setattr(daemon, 'run_server_daemon', lambda: pytest.fail('daemon started'))
    with pytest.raises(SystemExit, match=message):
        daemon.main()


def test_config_read_error(config_path, monkeypatch):
    config_path.mkdir(parents=True)
    with pytest.raises(SystemExit, match='Configuration error'):
        onboarding.prepare()


def test_setup_commands(config_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['spotify-cmd', 'init'])
    cli.main()
    config_path.write_text(config_path.read_text().replace('client_id =', 'client_id = id').replace(
        'client_secret =', 'client_secret = secret%value'))
    monkeypatch.setattr(sys, 'argv', ['spotify-cmd', 'config', 'check'])
    cli.main()
    output = capsys.readouterr().out
    assert 'Configuration valid' in output and 'secret%value' not in output
    calls = []
    monkeypatch.setattr(cli, 'authenticate', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, 'argv', ['spotify-cmd', 'auth', '--no-browser'])
    cli.main()
    assert calls == [{'no_browser': True}]


@pytest.mark.parametrize('fail', [False, True])
def test_auth_uses_same_cache_and_restores_umask(config_path, monkeypatch, fail):
    import spotipy.oauth2
    onboarding.initialize()
    config_path.write_text(config_path.read_text().replace('client_id =', 'client_id = id').replace(
        'client_secret =', 'client_secret = secret'))
    calls = []
    if fail:
        cache_dir = config_path.parent / 'cache'
        cache_dir.mkdir()
        (cache_dir / 'token-cache').write_text('{}')

    class OAuth:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def get_access_token(self, **kwargs):
            assert kwargs == {'as_dict': False}
            if fail:
                raise RuntimeError('offline')
            calls[0]['cache_handler'].save_token_to_cache({'access_token': 'test'})
            return 'test'

    monkeypatch.setattr(spotipy.oauth2, 'SpotifyOAuth', OAuth)
    previous = os.umask(0o022)
    try:
        if fail:
            with pytest.raises(RuntimeError, match='offline'):
                onboarding.authenticate(no_browser=True)
        else:
            onboarding.authenticate(no_browser=True)
            assert stat.S_IMODE((config_path.parent / 'cache/token-cache').stat().st_mode) == 0o600
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(previous)
    assert calls[0]['open_browser'] is False
    assert calls[0]['scope'] == onboarding.SCOPE


def test_help_and_versions_work_without_config(config_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': str(root / 'src')}
    for module, args in [('spotify_cmd_client.main', ['version']),
                         ('spotify_cmd_daemon.main', ['--version']),
                         ('spotify_cmd_client.main', ['--help'])]:
        result = subprocess.run([sys.executable, '-m', module, *args], env=env,
                                cwd=config_path.parent.parent, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert not config_path.exists()
