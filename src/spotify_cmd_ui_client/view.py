import curses
import time

from common.config import UI_COLOR_DEFAULTS
from .state import VIEW_TITLES, View


class CursesView:
    FOOTER = '↑/↓ Move  ←/→ Seek  Enter Play  Space Play/Pause  s Stop  h Shuffle  q Quit'
    BAR_PAIR = 1
    SELECTED_PAIR = 2
    PROGRESS_PAIR = 3
    TEXT_PAIR = 4
    PLAYING_PAIR = 5
    ERROR_PAIR = 6

    def __init__(self, colors=None, separator='●'):
        self.colors = UI_COLOR_DEFAULTS | (colors or {})
        self.separator = separator
        self.bar_style = curses.A_REVERSE
        self.selected_style = curses.A_REVERSE
        self.progress_style = curses.A_REVERSE
        self.text_style = curses.A_NORMAL
        self.playing_style = curses.A_BOLD
        self.error_style = curses.A_REVERSE

    def initialize_colors(self):
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(self.BAR_PAIR, self._color('bar_foreground'), self._color('bar_background'))
            curses.init_pair(self.SELECTED_PAIR, self._color('selected_foreground'), self._color('selected_background'))
            curses.init_pair(self.PROGRESS_PAIR, self._color('progress_foreground'), self._color('progress_background'))
            curses.init_pair(self.TEXT_PAIR, self._color('text_foreground'), -1)
            curses.init_pair(self.PLAYING_PAIR, self._color('playing_foreground'), -1)
            curses.init_pair(self.ERROR_PAIR, self._color('error_foreground'), self._color('error_background'))
            self.bar_style = curses.color_pair(self.BAR_PAIR)
            self.selected_style = curses.color_pair(self.SELECTED_PAIR)
            self.progress_style = curses.color_pair(self.PROGRESS_PAIR)
            self.text_style = curses.color_pair(self.TEXT_PAIR)
            self.playing_style = curses.color_pair(self.PLAYING_PAIR) | curses.A_BOLD
            self.error_style = curses.color_pair(self.ERROR_PAIR) | curses.A_BOLD
        except curses.error:
            pass

    def _color(self, setting):
        name = self.colors[setting]
        if name == 'default':
            return -1
        bright = name.startswith('bright_')
        base_name = name.removeprefix('bright_').upper()
        value = getattr(curses, f'COLOR_{base_name}')
        return value + 8 if bright and getattr(curses, 'COLORS', 8) >= 16 else value

    @staticmethod
    def _paint_row(screen, row, width, style):
        try:
            screen.chgat(row, 0, width, style)
        except curses.error:
            pass

    def draw(self, screen, state):
        screen.erase()
        height, width = screen.getmaxyx()
        self._draw_header(screen, state, width)
        if state.loading:
            self._draw_loading(screen, height, width)
        else:
            self._draw_items(screen, state, width)
        self._draw_footer(screen, state, height, width)
        screen.refresh()

    def _draw_header(self, screen, state, width):
        self._paint_row(screen, 0, width, self.bar_style)
        column = 0
        for index, title in enumerate(VIEW_TITLES[view] for view in View):
            tab = f' {index + 1} {title} '
            style = self._inverted(self.bar_style) | curses.A_BOLD if state.view.value == index else self.bar_style
            screen.addnstr(0, column, tab, max(width - column, 0), style)
            column += len(tab)

    @staticmethod
    def _draw_loading(screen, height, width):
        loading = 'LOADING'
        style = curses.A_BOLD if int(time.monotonic() * 2) % 2 else curses.A_NORMAL
        screen.addnstr(height // 2, max((width - len(loading)) // 2, 0), loading, width - 1, style)

    def _draw_items(self, screen, state, width):
        visible_items = state.items[state.first_visible:state.first_visible + state.visible_rows]
        for row, item in enumerate(visible_items):
            self._draw_item(screen, row, state.first_visible + row, item, state, width)

    def _draw_item(self, screen, row, index, item, state, width):
        playing = item.get('spotify_id') == state.playing_id
        selected = index == state.selected
        if selected:
            style = self.selected_style
            self._paint_row(screen, row + 1, width, style)
        elif playing:
            style = self.playing_style
        else:
            style = self.text_style
        marker = '▶ ' if playing else '  '
        duration = self._duration_label(item, state.view)
        label_width = max(width - len(duration) - 2, 0) if duration else max(width - 1, 0)
        label = self._truncate(f'{marker}{self._item_label(item, state.view, self.separator)}', label_width)
        screen.addnstr(row + 1, 0, label, label_width, style)
        if duration:
            self._add_text(screen, row + 1, width - len(duration) - 1, duration, width, style)

    @staticmethod
    def _item_label(item, view, separator='●'):
        name = item['name']
        if item.get('is_playable') is False:
            name += ' [unavailable]'
        artists = item.get('artists')
        if (view is View.ALBUMS or item.get('type') == 'albums') and artists:
            return f'{name}  {separator}  {artists}'
        if view is View.NOW_PLAYING and artists:
            return f'{name}  {separator}  {artists}'
        return name

    @classmethod
    def _duration_label(cls, item, view):
        duration_ms = item.get('duration_ms') if view is View.NOW_PLAYING else None
        return cls._format_time(duration_ms) if duration_ms is not None else ''

    @staticmethod
    def _truncate(text, width):
        if len(text) <= width:
            return text
        return '.' * width if width <= 3 else f'{text[:width - 3]}...'

    def _draw_footer(self, screen, state, height, width):
        if state.is_playing and state.duration_ms and not state.message_is_error:
            self._draw_progress(screen, state, height, width)
            return
        hint = '← Artists  ↑/↓ Move  Enter Play album  q Quit' if state.view is View.ARTISTS and state.artist_context else self.FOOTER
        footer = state.message or hint
        style = self.error_style if state.message_is_error else self.bar_style
        self._paint_row(screen, height - 1, width, style)
        screen.addnstr(height - 1, 0, footer, max(width - 1, 0), style)

    def _draw_progress(self, screen, state, height, width):
        ratio = min(max(state.progress_ms / state.duration_ms, 0), 1)
        filled = int(width * ratio)
        self._paint_row(screen, height - 1, width, self.progress_style)
        if filled:
            self._paint_row(screen, height - 1, filled, self.bar_style)
        label = f'{self._format_time(state.progress_ms)} / {self._format_time(state.duration_ms)}'
        column = max((width - len(label)) // 2, 0)
        self._draw_progress_label(screen, height, width, column, label, filled)

    def _draw_progress_label(self, screen, height, width, column, label, filled):
        passed_length = min(max(filled - column, 0), len(label))
        passed, remaining = label[:passed_length], label[passed_length:]
        self._add_text(screen, height - 1, column, passed, width, self.bar_style)
        self._add_text(
            screen, height - 1, column + passed_length, remaining, width,
            self.progress_style | curses.A_BOLD,
        )

    @staticmethod
    def _add_text(screen, row, column, text, width, style):
        """Draw text without addressing curses' inaccessible bottom-right cell."""
        available_width = max(width - column - 1, 0)
        if available_width:
            screen.addnstr(row, column, text, available_width, style)

    @staticmethod
    def _inverted(style):
        return style ^ curses.A_REVERSE

    @staticmethod
    def _format_time(milliseconds):
        seconds = milliseconds // 1000
        return f'{seconds // 60}:{seconds % 60:02d}'
