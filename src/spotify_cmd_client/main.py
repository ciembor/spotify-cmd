import socket
import argparse
import json
from .client import Client

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Client for controlling Spotify playback through a spotify-cmd-daemon.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Basic commands
    play_parser = subparsers.add_parser('play', help='start playback')
    pause_parser = subparsers.add_parser('pause', help='pause playback')
    next_parser = subparsers.add_parser('next', help='play next track')
    prev_parser = subparsers.add_parser('previous', help='play previous track')

    # Set commands
    set_parser = subparsers.add_parser('set', help='player settings')
    set_subparsers = set_parser.add_subparsers(dest='setting')

    # Shuffle
    shuffle_parser = set_subparsers.add_parser('shuffle', help='toggle shuffle')
    shuffle_parser.add_argument('state', choices=['on', 'off'], help='shuffle state')

    # Volume
    volume_parser = set_subparsers.add_parser('volume', help='set volume')
    volume_parser.add_argument('level', type=int, choices=range(0, 101), help='volume level from 0 to 100')

    # Get commands
    get_parser = subparsers.add_parser('get', help='get information')
    get_subparsers = get_parser.add_subparsers(dest='get_type')

    get_subparsers.add_parser('playlists', help='get playlists')
    get_subparsers.add_parser('albums', help='get albums')

    # Play specific item
    play_type_parser = play_parser.add_subparsers(dest='play_type')

    play_playlist_parser = play_type_parser.add_parser('playlist', help='play a specific playlist')
    play_playlist_parser.add_argument('name', type=str, help='playlist name')

    play_album_parser = play_type_parser.add_parser('album', help='play a specific album')
    play_album_parser.add_argument('name', type=str, help='album name')

    play_uri_parser = play_type_parser.add_parser('uri', help='play resource by spotify URI')
    play_uri_parser.add_argument('uri', type=str, help='spotify uri')

    find_parser = subparsers.add_parser('find', help='find items based on search query')
    find_parser.add_argument('search_type', choices=['album', 'artist', 'playlist', 'track', 'episode', 'show'], help='type of item to find')
    find_parser.add_argument('search_query', type=str, help='search query string')

    parser.add_argument('--format', choices=['json', 'text', 'verbose'], default='text', help='output format')

    args = parser.parse_args()

    payload = {
        'command': args.command,
        'setting': getattr(args, 'setting', None),
        'type': (getattr(args, 'get_type', None) or
                 getattr(args, 'play_type', None) or
                 getattr(args, 'search_type', None)),
        'value': (getattr(args, 'state', None) or
                  getattr(args, 'level', None) or
                  getattr(args, 'name', None) or
                  getattr(args, 'uri', None) or
                  getattr(args, 'search_query', None))
    }

    client = Client()
    if client.connect():
        client.send_command(payload)
        client.handle_response(getattr(args, 'format'))
        client.close()

if __name__ == "__main__":
    main()
