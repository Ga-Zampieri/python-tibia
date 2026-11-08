import ctypes
import threading
import time
from types import SimpleNamespace

from src import action_manager
from src.action_manager import ActionManager


def test_interface_click_keeps_the_cursor_on_the_button_until_after_release(monkeypatch):
    events = []
    down, up = action_manager.MOUSE_FLAGS["left"]
    user32 = SimpleNamespace(
        mouse_event=lambda flag, *_: events.append(flag),
        SetCursorPos=lambda x, y: events.append((x, y)),
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: events.append(seconds))
    am = ActionManager.__new__(ActionManager)
    am.lock = threading.RLock()
    am.client_to_screen = lambda pos: pos

    am.press_with_cursor((10, 20), "left")

    assert events[0] == (10, 20)
    assert events.index(down) < events.index(up)
    assert sum(isinstance(event, tuple) for event in events) == 1
    assert events[events.index(down) + 1] > 0.02
    assert events[-1] > 0.02


def fake_user32(monkeypatch, events):
    user32 = SimpleNamespace(
        mouse_event=lambda flag, *_: events.append(flag),
        SetCursorPos=lambda x, y: events.append((x, y)),
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: events.append(seconds))


def manager(foreground=True):
    am = ActionManager.__new__(ActionManager)
    am.lock = threading.RLock()
    am.client_to_screen = lambda pos: pos
    am.get_cursor = lambda: (7, 8)
    am.is_foreground = lambda: foreground
    am.focused = 0

    def focus():
        am.focused += 1
    am.focusWindow = focus
    return am


def waited(events):
    return sum(event for event in events if isinstance(event, float))


def test_quick_drag_waits_far_less_and_still_ends_on_the_destination(monkeypatch):
    events = []
    fake_user32(monkeypatch, events)
    down, up = action_manager.MOUSE_FLAGS["left"]
    am = manager()

    assert am.drag_with_cursor((10, 10), (90, 50), quick=True)

    assert am.focused == 0
    assert waited(events) < 0.2
    assert events.index(down) < events.index((90, 50)) < events.index(up)
    assert events[-1] == (7, 8)


def test_normal_drag_keeps_its_rhythm(monkeypatch):
    events = []
    fake_user32(monkeypatch, events)
    am = manager()

    assert am.drag_with_cursor((10, 10), (90, 50))

    assert am.focused == 1
    assert waited(events) > 0.5


def test_quick_drag_still_brings_the_game_to_the_front(monkeypatch):
    fake_user32(monkeypatch, [])
    am = manager(foreground=False)
    am.drag_with_cursor((10, 10), (90, 50), quick=True)
    assert am.focused == 1
