import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest


PACKAGE_NAME = 'spotify-cmd'


def run(command, *, env=None, cwd=None):
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


@pytest.mark.pypi
def test_pypi_package_installs_and_console_commands_run(tmp_path):
    """Validate the released package without importing code from this checkout."""
    released_version = version(PACKAGE_NAME)
    environment = tmp_path / 'installed-from-pypi'
    creation = run([sys.executable, '-m', 'venv', str(environment)])
    assert creation.returncode == 0, creation.stderr

    bin_dir = environment / ('Scripts' if os.name == 'nt' else 'bin')
    python = bin_dir / ('python.exe' if os.name == 'nt' else 'python')
    installation = run([
        str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
        '--no-cache-dir', f'{PACKAGE_NAME}=={released_version}',
    ])
    assert installation.returncode == 0, installation.stderr

    installed_version = run(
        [str(python), '-c', f"from importlib.metadata import version; print(version('{PACKAGE_NAME}'))"],
        cwd=tmp_path,
    )
    assert installed_version.returncode == 0
    assert installed_version.stdout.strip() == released_version

    client = bin_dir / ('spotify-cmd.exe' if os.name == 'nt' else 'spotify-cmd')
    daemon = bin_dir / ('spotify-cmd-daemon.exe' if os.name == 'nt' else 'spotify-cmd-daemon')
    ui = bin_dir / ('spotify-cmd-ui.exe' if os.name == 'nt' else 'spotify-cmd-ui')
    assert client.is_file()
    assert daemon.is_file()
    assert ui.is_file()

    for executable, version_args in ((client, ('version',)), (daemon, ('--version',)), (ui, ('--version',))):
        version_result = run(
            [str(executable), *version_args],
            cwd=tmp_path,
        )
        assert version_result.returncode == 0, version_result.stderr
        assert version_result.stdout.strip() == released_version

        help_result = run([str(executable), '--help'], cwd=tmp_path)
        assert help_result.returncode == 0, help_result.stderr
        assert 'usage:' in help_result.stdout.lower()

    config = tmp_path / 'config.ini'
    missing_socket = tmp_path / 'missing.sock'
    config.write_text(
        '[SPOTIFY]\nclient_id = test-client\nclient_secret = test-secret\n'
        f'[SPOTIFY_CMD_DAEMON]\nsocket_path = {missing_socket}\n'
    )
    command_env = os.environ | {'SPOTIFY_CMD_CONFIG': str(config)}
    unavailable_daemon = run([str(client), 'pause'], env=command_env, cwd=tmp_path)
    assert unavailable_daemon.returncode == 0
    assert 'Cannot connect to daemon.' in unavailable_daemon.stdout


@pytest.mark.pypi
def test_pypi_package_communicates_with_a_unix_socket_server_in_docker(tmp_path):
    """Run the published package in Linux and verify its complete socket exchange."""
    if run(['docker', 'info']).returncode != 0:
        pytest.skip('Docker daemon is not available')

    released_version = version(PACKAGE_NAME)
    tag = f'spotify-cmd-pypi-smoke:{released_version}'
    context = Path(__file__).parent / 'pypi_container'
    build = run([
        'docker', 'build', '--pull', '--build-arg', f'PACKAGE_VERSION={released_version}',
        '--tag', tag, str(context),
    ])
    assert build.returncode == 0, build.stderr
    execution = run(['docker', 'run', '--rm', '-e', f'PACKAGE_VERSION={released_version}', tag])
    assert execution.returncode == 0, execution.stderr
