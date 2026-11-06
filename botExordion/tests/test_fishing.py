from conftest import FakeActionManager
from src.fishing import Pesca


def test_fishing_attempts_each_water_three_times_without_blocking_input(monkeypatch):
    am = FakeActionManager()
    fishing = Pesca({"rod": [10, 20], "waters": [[30, 40]]})
    fishing.am = am
    original = am.left_click

    def left_click(pos):
        result = original(pos)
        if fishing.attempts == 2:
            fishing._stop_event.set()
        return result

    am.left_click = left_click
    monkeypatch.setattr(fishing, "_sleep_interruptible", lambda _seconds: True)
    monkeypatch.setattr("src.fishing.random.randint", lambda _low, _high: 0)

    fishing._run()

    assert am.calls == [("right", (10, 20)), ("left", (30, 40))] * 3
    assert fishing.attempts == 3
    assert am.block_calls == 0


def test_fishing_needs_rod_and_water(fake_am):
    fishing = Pesca({"rod": None, "waters": []})
    fishing.am = fake_am
    assert fishing.start() is False
