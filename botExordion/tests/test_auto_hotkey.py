import threading

import pytest

from src.auto_hotkey import AutoHotkey


def test_repeats_the_action_and_stops():
    calls = []
    three_calls = threading.Event()

    def action(key):
        calls.append(key)
        if len(calls) == 3:
            three_calls.set()

    repeater = AutoHotkey()
    assert repeater.start("f5", 0.01, action) is True
    assert three_calls.wait(timeout=1)
    repeater.stop()

    assert calls[:3] == ["f5", "f5", "f5"]
    assert repeater.is_running is False


@pytest.mark.parametrize("interval", ["0", "-1", "invalid"])
def test_rejects_invalid_interval(interval):
    with pytest.raises(ValueError):
        AutoHotkey().start("x", interval, lambda key: None)


def test_accepts_comma_as_decimal_separator():
    repeater = AutoHotkey()
    assert repeater.start("x", "0,5", lambda key: None) is True
    repeater.stop()
