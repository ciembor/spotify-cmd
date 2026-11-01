import curses
import time

from .state import View


class CursesView:
    FOOTER = '↑/↓ Move  ←/→ Seek  Enter Play  Space Play/Pause  s Stop  h Shuffle  q Quit'
    BAR_PAIR = 1
    SELECTED_PAIR = 2
    PROGRESS_PAIR = 3

    def __init__(self):
        self.bar_style = curses.A_REVERSE
        self.selected_style = curses.A_REVERSE
        self.progress_style = curses.A_REVERSE

    def initialize_colors(self):
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            bright_black = 8 if curses.COLORS >= 16 else curses.COLOR_BLACK
            dim_white = curses.COLOR_WHITE
            bright_white = 15 if curses.COLORS >= 16 else curses.COLOR_WHITE
            curses.init_pair(self.BAR_PAIR, curses.COLOR_BLACK, dim_white)
            curses.init_pair(self.SELECTED_PAIR, curses.COLOR_BLACK, bright_white)
            curses.init_pair(self.PROGRESS_PAIR, bright_white, bright_black)
            self.bar_style = curses.color_pair(self.BAR_PAIR)
            self.selected_style = curses.color_pair(self.SELECTED_PAIR)
            self.progress_style = curses.color_pair(self.PROGRESS_PAIR)
        except curses.error:
            pass

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
        for index, title in enumerate(('Albums', 'Playlists', 'Artists', 'Now playing')):
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
            style = curses.A_BOLD
        else:
            style = curses.A_NORMAL
        marker = '▶ ' if playing else '  '
        screen.addnstr(row + 1, 0, f'{marker}{self._item_label(item, state.view)}', width - 1, style)

    @staticmethod
    def _item_label(item, view):
        name = item['name']
        artists = item.get('artists')
        if view is View.ALBUMS and artists:
            return f'{name}  ●  {artists}'
        if view is View.NOW_PLAYING and artists:
            return f'{name}  ●  {artists}'
        return name

    def _draw_footer(self, screen, state, height, width):
        if state.is_playing and state.duration_ms:
            self._draw_progress(screen, state, height, width)
            return
        footer = state.message or self.FOOTER
        self._paint_row(screen, height - 1, width, self.bar_style)
        screen.addnstr(height - 1, 0, footer, max(width - 1, 0), self.bar_style)

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
