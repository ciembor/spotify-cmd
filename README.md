# 📻 spotify-cmd v0.1.16

`spotify-cmd` is a Spotify client that allows controlling the playback of **albums and playlists from a user's library** (based on names or Spotify URIs) and individual tracks (based solely on Spotify URIs). The application is intended for use with [spotifyd](https://github.com/Spotifyd/spotifyd), but it works with any Spotify-enabled device.

## Installation

Ensure you have Python 3 installed. Package is available on PyPi: https://pypi.org/project/spotify-cmd/. Install it using `pip3`:

```bash
pip3 install spotify-cmd
```

### Debian/Ubuntu (apt)

```bash
curl -fsSL https://maciej-ciemborowicz.eu/apt/spotify-cmd.gpg | sudo gpg --dearmor -o /usr/share/keyrings/spotify-cmd-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/spotify-cmd-archive-keyring.gpg] https://maciej-ciemborowicz.eu/apt ./" | sudo tee /etc/apt/sources.list.d/spotify-cmd.list
sudo apt update
sudo apt install spotify-cmd
```

After installing from apt, the daemon is managed by systemd. Create the config at `/var/lib/spotify-cmd/.config/spotify-cmd/config.ini`, then restart:

```bash
sudo systemctl restart spotify-cmd
sudo systemctl status spotify-cmd --no-pager
```

If the service stays inactive, you need a token cache at `/var/lib/spotify-cmd/.config/spotify-cmd/cache/token-cache`. You can either generate it by running a one-time OAuth flow as the service user, or copy it from a user cache.

```bash
sudo systemctl stop spotify-cmd
sudo -u spotify-cmd /usr/bin/spotify-cmd-daemon --foreground
# Complete the OAuth flow in your browser (use an SSH tunnel if remote).
sudo systemctl start spotify-cmd
```

Or copy an existing cache:

```bash
sudo install -d -o spotify-cmd -g spotify-cmd /var/lib/spotify-cmd/.config/spotify-cmd/cache
sudo cp ~/.config/spotify-cmd/cache/token-cache /var/lib/spotify-cmd/.config/spotify-cmd/cache/token-cache
sudo chown spotify-cmd:spotify-cmd /var/lib/spotify-cmd/.config/spotify-cmd/cache/token-cache
sudo systemctl restart spotify-cmd
```

If you want to run the client as a regular user (for example `pi`), add it to the `spotify-cmd` group so it can access the daemon socket:

```bash
sudo usermod -aG spotify-cmd <user>
```

### Headless spotifyd (Raspberry Pi, servers)

When using spotifyd on headless hosts, run it in the foreground under systemd and disable MPRIS to avoid DBus/X11 issues:

```ini
[global]
use_mpris = false
```

## Configuration

The application configuration should be located in `~/.config/spotify-cmd/config.ini`. Below is a detailed guide on each configuration option:

```ini
[SPOTIFY]
client_id = your_client_id
client_secret = your_client_secret
device_name = your_device_name  # optional; if omitted, uses the current active device
redirect_uri = http://localhost:8888/callback

[SPOTIFY_CMD_DAEMON]
socket_path = /run/spotify-cmd/spotify-cmd.sock
socket_buffer_size = 1024
```

* **client_id**, **client_secret** are required. Obtain these by creating an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/applications).
* **device_name** is optional. If set, `spotify-cmd-daemon` will force to use it even if another is active; if omitted, it uses the current active device.
* **redirect_uri** is used for Spotify authentication. If not set, it defaults to 'http://localhost:8888/callback'.
* **socket_path** specifies the Unix socket path for the daemon. Defaults to '/run/spotify-cmd/spotify-cmd.sock' on Linux and '/tmp/spotify-cmd-daemon.sock' on other systems.
* **socket_buffer_size** defines the buffer size for socket communication. Defaults to 1024.

## Commands

`spotify-cmd` offers the following commands:

* `get playlists`: Lists the user's playlists.
* `get albums`: Lists the user's albums.
* `play playlist <name>`, `play album <name>`, `play uri <spotify_uri>`: Plays a specific playlist, album, or resource by Spotify URI.
* `play`, `pause`, `next`, `previous`: Controls playback.
* `set shuffle <on|off>`: Toggles shuffle mode.
* `set volume <0-100>`: Sets the volume level.
* `find <search_type> <query>`: Searches for items on Spotify. Acceptable search types are `album`, `artist`, `playlist`, `track`, `episode`, and `show`.
* `version`: Prints the installed `spotify-cmd` version.

## Output Format

Select output format using the `--format` flag:

* `--format text`: Plain text output (default).
* `--format json`: Output in JSON format.
* `--format verbose`: Verbose text information.

## Usage Examples

``` bash
spotify-cmd get albums
spotify-cmd get playlists
spotify-cmd play album "Listening Tree"
spotify-cmd play uri spotify:album:5zKTfU3vyuZfLgtYRfJyza
spotify-cmd find artist "Nils Frahm"
```

## For Developers

Developers can create interfaces for `spotify-cmd-daemon` using `/run/spotify-cmd/spotify-cmd.sock` (Linux) or `/tmp/spotify-cmd-daemon.sock` (other systems). Socket handling and data format details are in the `./src/common` directory (there is no documentation).

Daemon helper:

* `spotify-cmd-daemon --version` prints the installed daemon version.

## Planned Features and Upcoming Development

* Displaying tracks from specific albums or playlists.
* MPRIS D-Bus interface support to reduce server queries.
* `spotify-cmd-ui`: A ncurses-based UI for track display and control, working with the same daemon.
* ~~Search functionality.~~ [Done in 0.1.4]
* Support for other resource types like artists.
* Config instructions after installation / creation of default config.

## License

This project is licensed under the terms of the GNU General Public License. Detailed information can be found in the [LICENSE.md](LICENSE.md) file.

## Author

Project created by Maciej Ciemborowicz.
