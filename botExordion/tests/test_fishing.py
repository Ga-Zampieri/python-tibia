from src.fishing import Pesca


class DummyActionManager:
    def __init__(self):
        self.right_clicks = []
        self.left_clicks = []
        self.fishing = None

    def is_valid(self):
        return True

    def move_mouse(self, position):
        return True

    def right_click(self, position):
        self.right_clicks.append(position)
        return True

    def left_click(self, position):
        self.left_clicks.append(position)
        if len(self.left_clicks) == 3:
            self.fishing._stop_event.set()
        return True


def test_fishing_attempts_each_water_three_times(monkeypatch):
    action_manager = DummyActionManager()
    fishing = Pesca(action_manager)
    action_manager.fishing = fishing
    fishing.varinha = (10, 20)
    fishing.watersCoords = [(30, 40)]
    monkeypatch.setattr(fishing, "_sleep_interruptible", lambda _seconds: True)
    monkeypatch.setattr("src.fishing.random.randint", lambda _low, _high: 0)

    fishing._run()

    assert len(action_manager.right_clicks) == 3
    assert len(action_manager.left_clicks) == 3


def test_capturing_waters_replaces_previous_coordinates(monkeypatch):
    fishing = Pesca(None)
    fishing.watersCoords = [(1, 2)]

    class FakeMouseListener:
        def __init__(self, on_click):
            self.on_click = on_click

        def start(self):
            self.on_click(30, 40, None, True)
            self.on_click(50, 60, None, True)

        def stop(self):
            pass

    monkeypatch.setattr("src.fishing.mouse.Listener", FakeMouseListener)

    assert fishing.getWaters(count=2, timeout=1) is True
    assert fishing.watersCoords == [(30, 40), (50, 60)]
