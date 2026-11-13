import copy

from conftest import FakeActionManager
from src.macros import MacroRunner
from src.settings import DEFAULT_PROFILE


def runner(am, macros, player=None, background=True):
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile["macros"] = macros
    profile["player_position"] = player
    profile["drag_in_background"] = background
    messages = []
    macro_runner = MacroRunner(profile, messages.append)
    macro_runner.am = am
    return macro_runner, messages


def normal(pos=(10, 20)):
    return {"mode": "normal", "pos": list(pos), "end": None}


def test_foreground_rune_uses_real_cursor_and_restores_it(monkeypatch):
    monkeypatch.setattr("src.macros.sleep", lambda _s: None)
    am = FakeActionManager(foreground=True)
    macro_runner, _ = runner(am, {"f5": normal()})

    assert macro_runner.execute("f5") is True
    assert am.calls == [("cursor_click", "right", (10, 20)), ("cursor", (3, 4))]
    assert am.block_calls == 1


def test_foreground_self_use_clicks_rune_then_player(monkeypatch):
    monkeypatch.setattr("src.macros.sleep", lambda _s: None)
    am = FakeActionManager(foreground=True)
    macro_runner, _ = runner(am, {"f5": {"mode": "self", "pos": [10, 20], "end": None}}, player=[30, 40])

    assert macro_runner.execute("f5") is True
    assert am.calls == [
        ("cursor_click", "right", (10, 20)),
        ("cursor_click", "left", (30, 40)),
        ("cursor", (3, 4)),
    ]


def test_background_rune_uses_messages_but_still_blocks_input(monkeypatch):
    monkeypatch.setattr("src.macros.sleep", lambda _s: None)
    am = FakeActionManager(foreground=False)
    macro_runner, _ = runner(am, {"f5": {"mode": "self", "pos": [10, 20], "end": None}}, player=[30, 40])

    assert macro_runner.execute("f5") is True
    assert am.calls == [("right", (10, 20)), ("left", (30, 40))]
    assert am.block_calls == 1


def test_failed_input_block_cancels_rune():
    am = FakeActionManager(block_ok=False)
    macro_runner, messages = runner(am, {"f5": normal()})

    assert macro_runner.execute("f5") is False
    assert am.calls == []
    assert "segurar o mouse" in messages[0]


def test_cursor_is_restored_after_error(monkeypatch):
    monkeypatch.setattr("src.macros.sleep", lambda _s: None)
    am = FakeActionManager(foreground=True)

    def explode(pos, button):
        raise RuntimeError("falha simulada")

    am.click_with_cursor = explode
    macro_runner, _ = runner(am, {"f5": normal()})

    assert macro_runner.execute("f5") is False
    assert am.calls == [("cursor", (3, 4))]


def test_self_use_without_player_position_is_refused():
    am = FakeActionManager()
    macro_runner, messages = runner(am, {"f5": {"mode": "self", "pos": [1, 2], "end": None}})

    assert macro_runner.execute("f5") is False
    assert am.block_calls == 0
    assert "player" in messages[0]


def test_drag_goes_by_messages_and_keeps_block_input():
    am = FakeActionManager(foreground=False)
    macro_runner, _ = runner(am, {"f6": {"mode": "drag", "pos": [1, 2], "end": [3, 4]}})

    assert macro_runner.execute("f6") is True
    assert am.calls == [("drag", (1, 2), (3, 4))]
    assert am.block_calls == 1


def test_drag_can_fall_back_to_real_cursor():
    am = FakeActionManager()
    macro_runner, _ = runner(am, {"f6": {"mode": "drag", "pos": [1, 2], "end": [3, 4]}}, background=False)

    assert macro_runner.execute("f6") is True
    assert am.calls == [("drag_cursor", (1, 2), (3, 4))]


def test_drag_without_end_point_is_refused():
    am = FakeActionManager()
    macro_runner, _ = runner(am, {"f6": {"mode": "drag", "pos": [1, 2], "end": None}})

    assert macro_runner.execute("f6") is False
    assert am.calls == []


def test_drag_with_the_game_in_front_uses_the_real_cursor_even_in_background_mode():
    am = FakeActionManager(foreground=True)
    macro_runner, _ = runner(am, {"f6": {"mode": "drag", "pos": [1, 2], "end": [3, 4]}})

    assert macro_runner.execute("f6") is True

    assert am.calls == [("drag_cursor", (1, 2), (3, 4))]
