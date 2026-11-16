import threading

import pytest

from src import auto_hotkey
from src.auto_hotkey import AutoHotkey, parse_interval


def run_until(entries, enough, timeout=2.0):
    calls = []
    done = threading.Event()

    def action(key):
        calls.append(key)
        if enough(calls):
            done.set()

    repeater = AutoHotkey()
    assert repeater.start(lambda: entries, action) is True
    assert done.wait(timeout)
    repeater.stop()
    assert repeater.is_running is False
    return calls


def test_repeats_one_key_and_stops():
    calls = run_until([("f5", 0.01)], lambda calls: len(calls) >= 3)
    assert calls[:3] == ["f5", "f5", "f5"]


def test_each_key_keeps_its_own_interval():
    calls = run_until([("f5", 0.01), ("f6", 0.2)], lambda calls: calls.count("f5") >= 15)
    # As duas disparam logo; depois a rápida dispara bem mais que a lenta.
    assert calls[:2] == ["f5", "f6"]
    assert calls.count("f6") <= 2


def test_keys_never_run_at_the_same_time():
    running = []
    overlaps = []
    calls = []
    done = threading.Event()

    def action(key):
        if running:
            overlaps.append(key)
        running.append(key)
        threading.Event().wait(0.01)
        running.pop()
        calls.append(key)
        if len(calls) >= 6:
            done.set()

    repeater = AutoHotkey()
    repeater.start(lambda: [("a", 0.01), ("b", 0.01), ("c", 0.01)], action)
    assert done.wait(2)
    repeater.stop()
    assert overlaps == []


def test_list_changes_while_running(monkeypatch):
    monkeypatch.setattr(auto_hotkey, "RELOAD_SECONDS", 0.01)
    entries = [("f5", 5.0)]
    calls = []
    added = threading.Event()

    def action(key):
        calls.append(key)
        if key == "f6":
            added.set()

    repeater = AutoHotkey()
    repeater.start(lambda: list(entries), action)
    entries.append(("f6", 5.0))  # tecla nova entra sem religar
    assert added.wait(1)
    repeater.stop()
    assert calls[:2] == ["f5", "f6"]


def test_empty_list_waits_without_doing_anything(monkeypatch):
    monkeypatch.setattr(auto_hotkey, "RELOAD_SECONDS", 0.01)
    calls = []
    repeater = AutoHotkey()
    repeater.start(lambda: [], calls.append)
    threading.Event().wait(0.05)
    assert repeater.is_running
    repeater.stop()
    assert calls == []


@pytest.mark.parametrize("interval", ["0", "-1", "invalid", None, "nan"])
def test_rejects_invalid_interval(interval):
    with pytest.raises(ValueError):
        parse_interval(interval)


def test_accepts_comma_as_decimal_separator():
    assert parse_interval("0,5") == 0.5
