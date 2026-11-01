"""Transient playback expectations used while Spotify Connect catches up."""

import time


class PlaybackTransition:
    """Protect the UI from stale playback events during a user action."""

    def __init__(self, context_grace_seconds, item_grace_seconds):
        self.context_grace_seconds = context_grace_seconds
        self.item_grace_seconds = item_grace_seconds
        self.expected_context_uri = None
        self.expected_context_deadline = None
        self.expected_item_deadline = None
        self.context_confirmed = False

    def expect_context(self, uri):
        self.expected_context_uri = uri
        self.expected_context_deadline = time.monotonic() + self.context_grace_seconds

    def expect_item(self, state, spotify_id):
        state.expected_playing_id = spotify_id
        self.expected_item_deadline = time.monotonic() + self.item_grace_seconds

    def stale_item(self, state, item):
        expected_id = state.expected_playing_id
        if expected_id is None:
            return False
        if state.matches_item(item, expected_id):
            state.expected_playing_id = None
            self.expected_item_deadline = None
            return False
        if self.expected_item_deadline and time.monotonic() < self.expected_item_deadline:
            return True
        state.expected_playing_id = None
        self.expected_item_deadline = None
        return False

    def stale_context(self, context):
        self.context_confirmed = False
        if self.expected_context_uri is None:
            return False
        if (context or {}).get('uri') == self.expected_context_uri:
            self.expected_context_uri = None
            self.expected_context_deadline = None
            self.context_confirmed = True
            return False
        if time.monotonic() < self.expected_context_deadline:
            return True
        self.expected_context_uri = None
        self.expected_context_deadline = None
        return False
