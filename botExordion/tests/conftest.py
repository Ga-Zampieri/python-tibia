import contextlib
import threading

import pytest


class FakeActionManager:
    """Grava as ações em vez de enviá-las a uma janela."""

    def __init__(self, foreground=True, block_ok=True):
        self.hwnd = 1
        self.foreground = foreground
        self.block_ok = block_ok
        self.calls = []
        self.lock = threading.RLock()
        self.block_calls = 0

    def is_valid(self):
        return True

    def is_foreground(self):
        return self.foreground

    def is_minimized(self):
        return False

    def title(self):
        return "Tibia"

    @contextlib.contextmanager
    def guarded(self):
        self.block_calls += 1
        yield self.block_ok

    def screen_to_client(self, pos):
        return (pos[0] - 100, pos[1] - 50)

    def contains_screen_point(self, pos):
        return pos[0] >= 100

    def get_cursor(self):
        return (3, 4)

    def set_cursor(self, pos):
        self.calls.append(("cursor", tuple(pos)))

    def click_with_cursor(self, pos, button):
        self.calls.append(("cursor_click", button, tuple(pos)))

    def left_click(self, pos):
        self.calls.append(("left", tuple(pos)))
        return True

    def right_click(self, pos):
        self.calls.append(("right", tuple(pos)))
        return True

    def drag(self, start, end):
        self.calls.append(("drag", tuple(start), tuple(end)))
        return True

    def drag_with_cursor(self, start, end):
        self.calls.append(("drag_cursor", tuple(start), tuple(end)))
        return True

    def press_key(self, name):
        self.calls.append(("key", name))
        return True

    def send_text(self, text):
        self.calls.append(("text", text))
        return True

    def turn(self, direction):
        self.calls.append(("turn", direction))
        return True


@pytest.fixture
def fake_am():
    return FakeActionManager()
