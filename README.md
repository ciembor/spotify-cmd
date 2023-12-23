# spotify-cmd v0.1.0

`spotify-cmd` is a Spotify client that allows controlling the playback of albums and playlists from a user's library (based on names or Spotify URIs) and individual tracks (based solely on Spotify URIs). The application is intended for use with [spotifyd](https://github.com/Spotifyd/spotifyd), but it works with any Spotify-enabled device.

## Installation

Ensure you have Python 3 installed. Then, install the project dependencies using `pip3`:

```bash
pip3 install -r ./src/spotify-cmd-daemon/requirements.txt
pip3 install -r ./src/spotify-cmd/requirements.txt
```

## Configuration

The application configuration should be located in `~/.config/spotify-cmd/config.ini`. Below is a detailed guide on each configuration option:

```ini
[SPOTIFY]
client_id = your_client_id       # Required. Your Spotify application's client ID.
client_secret = your_client_secret # Required. Your Spotify application's client secret.
device_name = your_device_name   # Required. The name of your Spotify playback device.
redirect_uri = http://localhost:8888/callback

[SPOTIFY_CMD_DAEMON]
socket_path = /tmp/spotify-cmd-daemon.sock
socket_buffer_size = 1024
```

## Commands

`spotify-cmd` offers the following commands:

* `play`, `pause`, `next`, `previous`: Controls playback.
* `set shuffle <on|off>`: Toggles shuffle mode.
* `set volume <0-100>`: Sets the volume level.
* `get playlists`: Lists the user's playlists.
* `get albums`: Lists the user's albums.
* `play playlist <name>`, `play album <name>`, `play uri <spotify_uri>`: Plays a specific playlist, album, or resource by Spotify URI.

## Output Format

Select output format using the `--format` flag:

`--format text`: Plain text output (default).
`--format json`: Output in JSON format.
`--format verbose`: Verbose text information.

## Usage Examples

``` bash
./bin/spotify-cmd get albums
./bin/spotify-cmd get playlists
./bin/spotify-cmd play album "Listening Tree"
./bin/spotify-cmd play playlist "Discover Weekly"
./bin/spotify-cmd play uri spotify:album:5zKTfU3vyuZfLgtYRfJyza
```

## For Developers

Developers can create interfaces for `spotify-cmd-daemon` using `/tmp/spotify-cmd-daemon.sock`. Socket handling and data format details are in the `./src/common` directory (there is no documentation).

## Planned Features and Upcoming Development

* Displaying tracks from specific albums or playlists.
* MPRIS D-Bus interface support to reduce server queries.
* `spotify-cmd-ui`: A ncurses-based UI for track display and control, working with the same daemon.
* Search functionality.
* Support for other resource types like artists.

## License

This project is licensed under the terms of the GNU General Public License. Detailed information can be found in the [LICENSE.md](LICENSE.md) file.

## Author

Project created by Maciej Ciemborowicz.
