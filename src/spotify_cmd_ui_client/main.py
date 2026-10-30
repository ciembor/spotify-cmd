import curses

from .controller import TuiController
from .gateway import SpotifyGateway
from .view import CursesView


class TuiApplication:
    """Composition root for the independent terminal UI client."""

    def __init__(self, client_factory=None):
        gateway = SpotifyGateway(client_factory) if client_factory else SpotifyGateway()
        self.controller = TuiController(gateway)
        self.view = CursesView()

    def run(self, screen):
        curses.curs_set(0)
        self.view.initialize_colors()
        screen.timeout(100)
        self.controller.start()
        try:
            while self._run_cycle(screen):
                pass
        finally:
            self.controller.close()

    def _run_cycle(self, screen):
        self.controller.tick()
        self._render(screen)
        return self._handle_key(screen.getch())

    def _render(self, screen):
        height, _ = screen.getmaxyx()
        self.controller.resize(height)
        self.view.draw(screen, self.controller.state)

    def _handle_key(self, key):
        if key in (ord('q'), 27):
            return False
        if key in (ord('1'), ord('2'), ord('3')):
            self.controller.select_view(key - ord('1'))
        elif key == curses.KEY_UP:
            self.controller.move(-1)
        elif key == curses.KEY_DOWN:
            self.controller.move(1)
        elif key in (curses.KEY_ENTER, 10, 13):
            self.controller.play_selected()
        elif key == ord(' '):
            self.controller.toggle_playback()
        elif key == ord('s'):
            self.controller.stop()
        elif key == ord('h'):
            self.controller.toggle_shuffle()
        return True


def main():
    curses.wrapper(TuiApplication().run)
