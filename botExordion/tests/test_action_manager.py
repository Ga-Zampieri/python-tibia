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
    am.settings = dict(action_manager.DEFAULT_INPUT)
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
    am.settings = dict(action_manager.DEFAULT_INPUT)
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
    assert waited(events) < 0.35
    assert events.index(down) < events.index((90, 50)) < events.index(up)
    assert events[-1] == (7, 8)


def test_message_drag_keeps_the_real_cursor_on_the_destination(monkeypatch):
    """O cliente solta onde está o cursor de verdade, então ele espera no destino."""
    events = []
    fake_user32(monkeypatch, events)
    am = manager(foreground=False)
    am._send = lambda message, wparam, lparam: events.append(("msg", message))

    assert am.drag((10, 10), (90, 50), quick=True)

    up = events.index(("msg", action_manager.win32con.WM_LBUTTONUP))
    assert events[0] == (90, 50)
    assert action_manager.DROP_GRACE in events[up:]
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


def test_quick_click_moves_for_real_and_waits_before_pressing(monkeypatch):
    events = []
    fake_user32(monkeypatch, events)
    down, up = action_manager.MOUSE_FLAGS["left"]
    am = manager()

    am.click_with_cursor((10, 20), "left")

    move = action_manager.MOUSEEVENTF_MOVE
    assert events[0] == (10, 20)
    assert events.index(move) < events.index(down) < events.index(up)
    between = events[events.index(move):events.index(down)]
    assert any(isinstance(event, float) and event >= 0.03 for event in between)
    assert events[-1] >= 0.03


def test_self_use_never_presses_left_before_the_cursor_reached_the_player(monkeypatch):
    events = []
    fake_user32(monkeypatch, events)
    right_down, right_up = action_manager.MOUSE_FLAGS["right"]
    left_down, _ = action_manager.MOUSE_FLAGS["left"]
    am = manager()

    am.click_with_cursor((10, 20), "right")
    am.click_with_cursor((50, 60), "left")

    assert events.index(right_up) < events.index((50, 60)) < events.index(left_down)


def guard_user32(monkeypatch, held, block_ok=True, mouse_held=False):
    """O caminho de reserva: sem segurar só o mouse, cai no BlockInput."""
    monkeypatch.setattr(action_manager.MouseBlocker, "start", lambda self: mouse_held)
    monkeypatch.setattr(action_manager.MouseBlocker, "stop", lambda self: None)
    calls = []
    user32 = SimpleNamespace(
        GetAsyncKeyState=lambda vk: 0x8000 if vk in held else 0,
        BlockInput=lambda on: calls.append(("block", bool(on))) or block_ok,
        keybd_event=lambda vk, scan, flags, extra: calls.append(("key", vk, flags)),
        MapVirtualKeyW=lambda vk, kind: 0,
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    return calls


def test_keys_held_when_input_is_blocked_are_released_afterwards(monkeypatch):
    shift, up_arrow, f2 = 0xA0, 0x26, 0x71
    calls = guard_user32(monkeypatch, {shift, up_arrow, f2})
    am = manager()

    with am.guarded() as blocked:
        assert blocked
        assert calls == [("block", True)]

    keyup = action_manager.KEYEVENTF_KEYUP
    extended = action_manager.KEYEVENTF_EXTENDEDKEY
    assert calls[1] == ("block", False)
    assert set(calls[2:]) == {("key", up_arrow, keyup | extended), ("key", f2, keyup), ("key", shift, keyup)}


def test_nothing_is_released_when_nothing_was_held(monkeypatch):
    calls = guard_user32(monkeypatch, set())
    with manager().guarded():
        pass
    assert calls == [("block", True), ("block", False)]


def test_without_block_no_key_is_touched(monkeypatch):
    calls = guard_user32(monkeypatch, {0xA0}, block_ok=False)
    with manager().guarded() as blocked:
        assert not blocked
    assert [call for call in calls if call[0] == "key"] == []


def test_mouse_buttons_are_never_released_by_the_guard(monkeypatch):
    calls = guard_user32(monkeypatch, {0x01, 0x02, 0x10, 0x5B})
    with manager().guarded():
        pass
    assert [call for call in calls if call[0] == "key"] == []


# ---------- prioridade ----------

def test_the_most_urgent_waiting_action_gets_the_mouse_first():
    lock = action_manager.PriorityLock()
    order = []
    lock.acquire()

    def wait_for_lock(level, name, ready):
        with action_manager.priority(level):
            ready.set()
            with lock:
                order.append(name)

    threads = []
    for level, name in (("loot", "loot"), ("fishing", "pesca"), ("heal", "cura")):
        ready = threading.Event()
        thread = threading.Thread(target=wait_for_lock, args=(level, name, ready))
        thread.start()
        ready.wait()
        threads.append(thread)
        time.sleep(0.05)  # garante que cada um já está na fila

    lock.release()
    for thread in threads:
        thread.join(timeout=2)

    assert order == ["cura", "loot", "pesca"]


def test_priority_lock_is_reentrant_and_gives_up_after_the_timeout():
    lock = action_manager.PriorityLock()
    with lock:
        with lock:
            pass
        result = []
        other = threading.Thread(target=lambda: result.append(lock.acquire(timeout=0.05)))
        other.start()
        other.join()
    assert result == [False]
    assert lock.acquire(timeout=0.05)
    lock.release()


# ---------- segurar só o mouse ----------

class FakeListener:
    made = []

    def __init__(self, win32_event_filter):
        self.filter = win32_event_filter
        self.running = False
        FakeListener.made.append(self)

    def start(self):
        self.running = True

    def wait(self):
        pass

    def stop(self):
        self.running = False

    def suppress_event(self):
        raise RuntimeError("suprimido")


def test_only_the_physical_mouse_is_held_and_a_swallowed_release_comes_back(monkeypatch):
    import pynput.mouse
    FakeListener.made = []
    monkeypatch.setattr(pynput.mouse, "Listener", FakeListener)
    events = []
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(
        mouse_event=lambda flag, *_: events.append(flag))), raising=False)
    blocker = action_manager.MouseBlocker()

    assert blocker.start()
    hook = FakeListener.made[0].filter
    assert hook(0x0200, SimpleNamespace(flags=1)) is True  # movimento do próprio bot passa
    for message in (0x0200, 0x0202):  # movimento e soltar físicos não passam
        try:
            hook(message, SimpleNamespace(flags=0))
            raise AssertionError("deveria ter sido suprimido")
        except RuntimeError:
            pass
    blocker.stop()

    assert not FakeListener.made[0].running
    assert events == [action_manager.MOUSE_FLAGS["left"][1]]


def test_holding_the_mouse_does_not_touch_the_keyboard(monkeypatch):
    calls = guard_user32(monkeypatch, {0xA0, 0x26}, mouse_held=True)
    with manager().guarded() as held:
        assert held
    assert calls == []


# ---------- mensagem ou cursor ----------

def test_auto_mode_uses_messages_only_with_the_game_behind():
    am = manager(foreground=False)
    assert action_manager.use_messages(am, background=True)
    assert not action_manager.use_messages(am, background=False)
    am.is_foreground = lambda: True
    assert not action_manager.use_messages(am, background=True)


def test_diagnostic_mode_logs_each_action(monkeypatch, caplog):
    am = manager(foreground=False)
    am.settings["diagnostic"] = True
    am.right_click = lambda pos: True
    with caplog.at_level("INFO"):
        action_manager.click_item(am, (5, 6), "right")
    assert "clique right (5, 6) por mensagem" in caplog.text
