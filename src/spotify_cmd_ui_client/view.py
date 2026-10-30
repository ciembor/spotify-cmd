import curses
import time


class CursesView:
    FOOTER = '1 Albums  2 Playlists  3 Now playing  ↑/↓ Move  Enter Play  Space Play/Pause  s Stop  h Shuffle  q Quit'
    BAR_PAIR = 1
    SELECTED_PAIR = 2

    def __init__(self):
        self.bar_style = curses.A_REVERSE
        self.selected_style = curses.A_REVERSE

    def initialize_colors(self):
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            dim_white = curses.COLOR_WHITE
            bright_white = 15 if curses.COLORS >= 16 else curses.COLOR_WHITE
            curses.init_pair(self.BAR_PAIR, curses.COLOR_BLACK, dim_white)
            curses.init_pair(self.SELECTED_PAIR, curses.COLOR_BLACK, bright_white)
            self.bar_style = curses.color_pair(self.BAR_PAIR)
            self.selected_style = curses.color_pair(self.SELECTED_PAIR) | curses.A_BOLD
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
        self._draw_header(screen, state.title, width)
        if state.loading:
            self._draw_loading(screen, height, width)
        else:
            self._draw_items(screen, state, width)
        self._draw_footer(screen, state.message, height, width)
        screen.refresh()

    def _draw_header(self, screen, title, width):
        self._paint_row(screen, 0, width, self.bar_style)
        screen.addnstr(0, 0, f' spotify-cmd-ui  |  {title} ', width - 1, self.bar_style)

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
        style = self.selected_style if index == state.selected else curses.A_NORMAL
        if index == state.selected:
            self._paint_row(screen, row + 1, width, style)
        if playing:
            style |= curses.A_BOLD
        detail = item.get('artists') or item.get('owner') or ''
        marker = '▶ ' if playing else '  '
        screen.addnstr(row + 1, 0, f"{marker}{item['name']}  {detail}", width - 1, style)

    def _draw_footer(self, screen, message, height, width):
        footer = message or self.FOOTER
        self._paint_row(screen, height - 1, width, self.bar_style)
        screen.addnstr(height - 1, 0, footer, width - 1, self.bar_style)
