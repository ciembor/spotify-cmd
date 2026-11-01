import pytest

from spotify_cmd_ui_client.controller import LoadResult, SeekResult, TuiController
from spotify_cmd_ui_client.state import TuiState


@pytest.fixture
def ui():
    controller = TuiController()
    controller.state.show_playing_context('spotify:playlist:new', 'New', 'playlist')
    yield controller
    controller.close()


def test_delayed_list_cannot_overwrite_a_newer_playback_event(ui):
    ui._load_token = 1
    ui._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'new'}, 'context': {'uri': 'spotify:playlist:new'},
    }})
    ui._results.put(LoadResult(1, 'tracks', 'spotify:playlist:new', None, {
        'tracks': [{'spotify_id': 'new'}, {'spotify_id': 'old'}], 'playing_id': 'old',
    }))
    ui.tick()
    assert ui.state.playing_id == 'new'
    assert len(ui.state.items) == 2
    assert not ui.state.loading


def test_reconnect_accepts_restarted_daemon_revisions(ui):
    ui.state.latest_state_revision = 100
    ui.start_load = lambda: None
    ui._events.put({'event': 'connection_restored'})
    ui._events.put({'event': 'state_changed', 'state_revision': 1, 'state': {'item': {'id': 'new'}}})
    ui.tick()
    assert ui.state.playback_id == 'new'
    assert ui.state.latest_state_revision == 1


def test_old_context_does_not_change_marker_or_progress(ui):
    ui.state.playback_id = ui.state.playing_id = 'new'
    ui.state.progress_ms = 0
    ui._expect_context('spotify:playlist:new')
    ui._events.put({'event': 'state_changed', 'state': {
        'item': {'id': 'old'}, 'progress_ms': 45000, 'context': {'uri': 'spotify:playlist:old'},
    }})
    ui.tick()
    assert ui.state.playback_id == 'new'
    assert ui.state.progress_ms == 0


def test_seek_error_does_not_resend_the_failed_request(ui):
    ui._pending_seek_target = 10000
    ui._seek_in_flight = True
    ui._seek_results.put(SeekResult(1, 10000, {'error': 'denied'}))
    ui.tick()
    assert not ui._seeking
    assert ui.state.message == 'denied'


def test_equal_disc_and_track_numbers_do_not_identify_a_song():
    state = TuiState(items=[{'spotify_id': 'wanted', 'track_number': 1, 'disc_number': 1}])
    assert not state.matches_item({'id': 'other', 'track_number': 1, 'disc_number': 1}, 'wanted')
    state.update_playing_item({'id': 'other', 'track_number': 1, 'disc_number': 1})
    assert state.playing_id == 'other'


def test_delayed_list_cannot_undo_an_explicit_play(ui):
    ui._load_token = 1
    ui._apply_play({'notification': 'started'}, 'new')
    ui._results.put(LoadResult(1, 'tracks', 'spotify:playlist:new', None, {
        'tracks': [{'spotify_id': 'new'}], 'playing_id': 'old',
    }))
    ui.tick()
    assert ui.state.playing_id == 'new'
