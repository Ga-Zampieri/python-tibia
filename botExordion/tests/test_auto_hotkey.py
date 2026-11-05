import threading

import pytest

from src.auto_hotkey import AutoHotkey


def test_auto_hotkey_repeats_and_stops(monkeypatch):
    calls = []
    three_presses = threading.Event()

    class FakeController:
        def press(self, key):
            calls.append(("press", key))
            if len(calls) == 5:
                three_presses.set()

        def release(self, key):
            calls.append(("release", key))

    monkeypatch.setattr("src.auto_hotkey.keyboard.Controller", FakeController)
    auto_hotkey = AutoHotkey()

    assert auto_hotkey.start("x", 0.01) is True
    assert three_presses.wait(timeout=1)
    auto_hotkey.stop()

    assert calls[:6] == [
        ("press", auto_hotkey._key),
        ("release", auto_hotkey._key),
        ("press", auto_hotkey._key),
        ("release", auto_hotkey._key),
        ("press", auto_hotkey._key),
        ("release", auto_hotkey._key),
    ]
    assert auto_hotkey.is_running is False


@pytest.mark.parametrize("interval", ["0", "-1", "invalid"])
def test_auto_hotkey_rejects_invalid_interval(interval):
    with pytest.raises(ValueError):
        AutoHotkey().start("x", interval)


def test_auto_hotkey_rejects_unknown_key():
    with pytest.raises(ValueError, match="Hotkey inválida"):
        AutoHotkey().start("not-a-key", 1)
