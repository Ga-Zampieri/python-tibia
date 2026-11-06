import numpy as np
import pytest

from conftest import FakeActionManager
from src.bot import BotController
from src.click_capture import ClickCapture
from src.settings import ProfileStore


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setattr("src.bot.beep", lambda: None)
    monkeypatch.setattr("src.macros.sleep", lambda _s: None)
    frames = {"frame": None}
    controller = BotController(
        store=ProfileStore(tmp_path, tmp_path / "missing.json"),
        capture=lambda hwnd: frames["frame"],
        list_windows=lambda: [],
    )
    controller.frames = frames
    controller._set_action_manager(FakeActionManager())
    controller.profile["macros"]["f5"] = {"mode": "normal", "pos": [1, 2], "end": None}
    controller._next_window_scan = float("inf")
    yield controller
    controller.stop_all(announce=False)


def drain(bot):
    keys = []
    while not bot._actions.empty():
        keys.append(bot._actions.get_nowait())
    return keys


def battle_frame(rows=2):
    frame = np.zeros((240, 200, 3), dtype=np.uint8)
    for index in range(rows):
        y = 40 + 30 * index
        frame[y + 14:y + 18, 30:130] = (0, 200, 0)
        frame[y + 4:y + 10, 30:60 + 10 * index] = (220, 220, 220)
    return frame


def test_hotkey_only_fires_with_game_in_foreground(bot):
    bot.macros_on = True
    bot.am.foreground = False
    bot.on_key("f5", False)
    assert drain(bot) == []

    bot.am.foreground = True
    bot.on_key("f5", False)
    assert drain(bot) == ["f5"]


def test_hotkey_ignored_while_macros_are_off(bot):
    bot.on_key("f5", False)
    assert drain(bot) == []


def test_esc_is_global_and_stops_everything(bot):
    bot.macros_on = True
    bot.alarm_on = True
    bot.am.foreground = False

    bot.on_key("esc", False)

    for _ in range(100):
        if not bot.macros_on:
            break
        bot._shutdown.wait(0.01)
    assert bot.macros_on is False and bot.alarm_on is False


def test_shift_f1_toggles_macros(bot):
    bot.on_key("f1", True)
    assert bot.macros_on is True
    bot.on_key("f1", True)
    assert bot.macros_on is False


def test_repeater_reaches_macro_with_game_in_background(bot):
    bot.am.foreground = False
    assert bot.run_action("f5") is True
    assert bot.am.calls == [("right", (1, 2))]


def test_run_action_sends_plain_keys_only_to_the_game(bot):
    bot.run_action("f12")
    assert bot.am.calls == [("key", "f12")]


def test_run_action_speaks_anything_else(bot):
    bot.run_action("exura")
    assert bot.am.calls == [("text", "exura")]


def test_modules_refuse_to_start_without_a_window(bot):
    bot._set_action_manager(None)
    assert bot.set_module("macros", True) is False


def test_training_needs_a_region(bot):
    assert bot.set_module("training", True) is False


def test_new_window_reaches_every_module(bot):
    other = FakeActionManager()
    bot._set_action_manager(other)
    assert bot.fishing.am is other
    assert bot.macros.am is other
    assert bot.survival.am is other
    assert bot.rune_maker.am is other


def test_training_clicks_battle_list(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=2)
    assert bot.set_module("training", True) is True

    bot.vision_tick(10.0)

    assert len(bot.am.calls) == 1 and bot.am.calls[0][0] == "left"


def test_training_never_attacks_a_name_outside_the_list(bot):
    bot.profile["training"]["mode"] = "normal"
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=1)
    bot.learn_visible_names()
    frame = np.zeros((240, 200, 3), dtype=np.uint8)
    frame[54:58, 30:130] = (0, 200, 0)
    frame[42:50, 30:120:2] = (220, 220, 220)
    bot.frames["frame"] = frame
    bot.set_module("training", True)

    bot.vision_tick(10.0)

    assert bot.am.calls == []


def test_alarm_stops_afk_modules_but_keeps_macros_and_survival(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=1)
    bot.set_module("alarm", True)
    bot.set_module("training", True)
    bot.macros_on = True
    bot.survival_on = True
    bot.vision_tick(10.0)

    bot.frames["frame"] = battle_frame(rows=3)
    bot.vision_tick(20.0)

    assert bot.training_on is False
    assert bot.macros_on is True and bot.survival_on is True


def test_missing_frame_does_not_click(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.set_module("training", True)
    bot.frames["frame"] = None

    bot.vision_tick(10.0)

    assert bot.am.calls == []


def test_old_coordinates_are_converted_once(bot):
    bot.profile["legacy_screen_coords"] = True
    bot.profile["player_position"] = [300, 150]
    bot.profile["macros"] = {"f5": {"mode": "drag", "pos": [110, 60], "end": [120, 70]}}

    bot._migrate_legacy_coords()
    bot._migrate_legacy_coords()

    assert bot.profile["player_position"] == [200, 100]
    assert bot.profile["macros"]["f5"] == {"mode": "drag", "pos": [10, 10], "end": [20, 20]}


def test_region_is_saved_relative_to_the_window(bot):
    assert bot.set_region_from_screen("battle", (300, 150, 180, 200)) is True
    assert bot.profile["training"]["region"] == [200, 100, 180, 200]


def test_tiny_battle_region_is_refused(bot):
    assert bot.set_region_from_screen("battle", (300, 150, 10, 10)) is False


def test_settings_survive_a_restart(bot, tmp_path):
    bot.profile["fishing"]["rod"] = [7, 8]
    bot.save()
    reopened = ProfileStore(tmp_path, tmp_path / "missing.json").load(bot.profile_name)
    assert reopened["fishing"]["rod"] == [7, 8]


def test_click_outside_the_game_does_not_count(bot):
    capture = ClickCapture(bot.am, 1, 1, lambda n: None, lambda points: None)

    assert capture._on_click(50, 50, None, True) is None
    assert capture.points == []
    assert capture._on_click(150, 100, None, True) is False
    assert capture.points == [[50, 50]]
