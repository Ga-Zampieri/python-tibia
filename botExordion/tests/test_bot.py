import json

import numpy as np
import pytest

from conftest import FakeActionManager
from src.bot import BotController
from src.click_capture import ClickCapture
from src.loot import encode_sprite
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
    controller._in_background = lambda target, *args: target(*args)
    yield controller
    controller.stop_all(announce=False)


def drain(bot):
    labels = []
    while not bot._actions.empty():
        labels.append(bot._actions.get_nowait()[3])
    return labels


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
    bot.on_key("f5")
    assert drain(bot) == []

    bot.am.foreground = True
    bot.on_key("f5")
    assert drain(bot) == ["f5"]


def test_hotkey_ignored_while_macros_are_off(bot):
    bot.on_key("f5")
    assert drain(bot) == []


def test_esc_is_global_and_stops_everything(bot):
    bot.macros_on = True
    bot.alarm_on = True
    bot.am.foreground = False

    bot.on_key("esc")

    for _ in range(100):
        if not bot.macros_on:
            break
        bot._shutdown.wait(0.01)
    assert bot.macros_on is False and bot.alarm_on is False


def test_shift_f1_toggles_macros(bot):
    bot.on_key("f1", {"shift"})
    assert bot.macros_on is True
    bot.on_key("f1", {"shift"})
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


def test_module_hotkey_toggles_fishing_with_game_in_background(bot):
    bot.profile["fishing"].update(rod=[1, 2], waters=[[3, 4]])
    bot.profile["module_hotkeys"]["fishing"] = "ctrl+f2"
    bot.am.foreground = False

    bot.on_key("f2", {"ctrl"})
    assert bot.status()["fishing"][0] is True

    bot.on_key("f2", {"ctrl"})
    assert bot.status()["fishing"][0] is False


def test_holding_the_hotkey_does_not_flip_the_module(bot):
    bot.on_key("f1", {"shift"})
    bot.on_key("f1", {"shift"}, True)
    bot.on_key("f1", {"shift"}, True)
    assert bot.macros_on is True


def test_module_toggle_leaves_the_keyboard_hook(bot):
    calls = []
    bot._in_background = lambda target, *args: calls.append((target, args))

    bot.on_key("f1", {"shift"})

    assert calls == [(bot._toggle_module, ("macros",))]
    assert bot.macros_on is False


def test_module_without_hotkey_ignores_a_bare_modifier_combo(bot):
    bot.on_key("", set())
    assert bot.macros_on is False


def test_captured_hotkey_is_saved_and_works(bot):
    bot.capture_module_hotkey("survival")
    bot.on_key("f3", {"shift", "ctrl"})

    assert bot.profile["module_hotkeys"]["survival"] == "ctrl+shift+f3"
    assert bot.store.load(bot.profile_name)["module_hotkeys"]["survival"] == "ctrl+shift+f3"
    assert bot.survival_on is False

    bot.on_key("f3", {"shift", "ctrl"})
    assert bot.survival_on is True


def test_key_being_captured_does_not_fire_a_macro(bot):
    bot.macros_on = True
    bot.capture_module_hotkey("alarm")
    bot.on_key("f5", {"shift"})
    assert drain(bot) == []


def test_hotkey_already_in_use_is_refused(bot):
    bot.capture_module_hotkey("fishing")
    bot.on_key("f1", {"shift"})
    assert bot.profile["module_hotkeys"]["fishing"] == ""
    assert bot.profile["module_hotkeys"]["macros"] == "shift+f1"

    bot.capture_module_hotkey("fishing")
    bot.on_key("f5")
    assert bot.profile["module_hotkeys"]["fishing"] == ""


def test_macro_cannot_take_a_module_hotkey(bot):
    bot.profile["module_hotkeys"]["fishing"] = "f7"
    assert bot.capture_macro("f7", "normal") is False


def test_esc_during_capture_keeps_old_hotkey_and_still_stops_everything(bot):
    bot.macros_on = True
    bot.capture_module_hotkey("macros")

    bot.on_key("esc")

    assert bot.profile["module_hotkeys"]["macros"] == "shift+f1"
    assert bot.macros_on is False
    bot.on_key("f9")
    assert bot.profile["module_hotkeys"]["macros"] == "shift+f1"


def test_cleared_hotkey_stops_working(bot):
    bot.clear_module_hotkey("macros")
    bot.on_key("f1", {"shift"})
    assert bot.macros_on is False


def test_rune_maker_warns_even_with_alarm_module_off(bot):
    bot.rune_maker.alert("acabou")

    kinds = []
    while not bot.events.empty():
        kinds.append(bot.events.get_nowait()[0])
    assert "alarm" in kinds


def test_rune_maker_reads_the_game_frame(bot):
    bot.frames["frame"] = battle_frame()
    assert bot.rune_maker.get_frame() is bot.frames["frame"]
    bot._set_action_manager(None)
    assert bot.rune_maker.get_frame() is None


def loot_ready(bot):
    bot.profile["loot"].update(grid=[10, 10, 2, 1], destination=[300, 300], items=["x"])
    bot.looter.start = lambda: True


def test_loot_hotkey_only_acts_with_game_in_front(bot):
    started = []
    loot_ready(bot)
    bot.looter.start = lambda: started.append(True) or True
    bot.profile["module_hotkeys"]["loot"] = "f8"

    bot.am.foreground = False
    bot.on_key("f8")
    assert started == []

    bot.am.foreground = True
    bot.on_key("f8")
    assert started == [True]


def test_loot_says_what_is_missing(bot):
    assert bot.set_module("loot", True) is False


def test_learning_loot_skips_empty_and_known_slots(bot):
    frame = np.full((100, 120, 3), 40, dtype=np.uint8)
    frame[10:42, 10:42] = np.arange(32, dtype=np.uint8)[:, None, None] * 7
    bot.frames["frame"] = frame
    bot.profile["loot"]["grid"] = [10, 10, 2, 1]

    bot.learn_loot("items")
    bot.learn_loot("items")
    bot.learn_loot("bags")

    assert len(bot.profile["loot"]["items"]) == 1
    assert bot.profile["loot"]["bags"] == []
    bot.remove_loot("items", 0)
    assert bot.profile["loot"]["items"] == []


def test_esc_stops_the_loot(bot):
    stopped = []
    bot.looter.stop = lambda: stopped.append(True)
    bot.on_key("esc")
    assert stopped == [True]


def test_extra_loot_press_does_not_cancel_a_running_loot(bot):
    loot_ready(bot)
    stopped = []
    bot.looter.stop = lambda: stopped.append(True)
    bot.profile["module_hotkeys"]["loot"] = "f8"
    type(bot.looter).is_running, original = property(lambda self: True), type(bot.looter).is_running
    try:
        bot.on_key("f8")
    finally:
        type(bot.looter).is_running = original
    assert stopped == []


def test_loot_list_goes_from_one_profile_to_another(bot, tmp_path):
    sprite = encode_sprite(np.full((32, 32, 3), 90, dtype=np.uint8))
    bot.profile["loot"].update(items=[sprite], grid=[1, 2, 4, 1], destination=[5, 6])
    path = tmp_path / "lista.json"
    bot.export_loot(path)
    assert "grid" not in path.read_text(encoding="utf-8")

    bot.profile["loot"].update(items=[])
    bot.import_loot(path)

    assert bot.profile["loot"]["items"] == [sprite]
    assert bot.store.load(bot.profile_name)["loot"]["items"] == [sprite]


def test_bad_loot_list_changes_nothing(bot, tmp_path):
    path = tmp_path / "lista.json"
    path.write_text("isso não é json", encoding="utf-8")
    bot.import_loot(path)
    bot.import_loot(tmp_path / "nao_existe.json")
    assert bot.profile["loot"]["items"] == []


def captured_at(bot, point):
    """Roda a captura de um clique como se o usuário tivesse clicado em point."""
    prompts = {}
    bot._begin_capture = lambda prompt, count, done: prompts.update(done=done) or True
    return lambda call: (call(), prompts["done"]([point]))


def test_backpacks_are_added_and_captured_again(bot):
    config = bot.profile["loot"]
    capture = captured_at(bot, [9, 9])

    capture(lambda: bot.capture_loot_destination(0))
    capture(lambda: bot.capture_loot_destination(1))
    assert config["destination"] == [9, 9]
    assert config["extra_destinations"] == [[9, 9]]

    capture = captured_at(bot, [8, 8])
    capture(lambda: bot.capture_loot_destination(1))
    assert config["extra_destinations"] == [[8, 8]]


def test_route_is_saved_and_cleared_with_the_item(bot):
    sprite = encode_sprite(np.full((32, 32, 3), 90, dtype=np.uint8))
    config = bot.profile["loot"]
    config.update(items=[sprite], destination=[1, 1], extra_destinations=[[2, 2]])

    bot.route_loot(0, 1)
    assert bot.store.load(bot.profile_name)["loot"]["routes"] == {sprite: 1}
    bot.route_loot(0, 0)
    assert config["routes"] == {}

    bot.route_loot(0, 1)
    bot.remove_loot("items", 0)
    assert config["items"] == [] and config["routes"] == {}


def test_removing_a_backpack_is_saved(bot):
    bot.profile["loot"].update(destination=[1, 1], extra_destinations=[[2, 2]], routes={"a": 1})
    bot.remove_loot_destination(1)
    saved = bot.store.load(bot.profile_name)["loot"]
    assert saved["extra_destinations"] == [] and saved["routes"] == {}


def test_old_profile_without_backpacks_keeps_working(tmp_path):
    from src.settings import DEFAULT_PROFILE, merge_defaults
    profile = merge_defaults(DEFAULT_PROFILE, {"loot": {"destination": [1, 2], "items": ["x"], "bags": []}})
    assert profile["loot"]["destination"] == [1, 2]
    assert profile["loot"]["extra_destinations"] == [] and profile["loot"]["routes"] == {}


def test_profile_travels_whole_and_arrives_as_a_new_profile(bot, tmp_path):
    sprite = encode_sprite(np.full((32, 32, 3), 90, dtype=np.uint8))
    bot.profile["fishing"]["rod"] = [7, 8]
    bot.profile["module_hotkeys"]["loot"] = "f5"
    bot.profile["loot"].update(items=[sprite], extra_destinations=[[2, 2]], routes={sprite: 1})
    path = tmp_path / "perfil.json"
    original = bot.profile_name
    bot.export_profile(path)

    assert bot.import_profile(path)

    assert bot.profile_name == f"{original} (2)"
    assert bot.profile["fishing"]["rod"] == [7, 8]
    assert bot.profile["module_hotkeys"]["loot"] == "f5"
    assert bot.profile["loot"]["routes"] == {sprite: 1}
    assert bot.store.load(original)["fishing"]["rod"] == [7, 8]
    assert sorted(bot.store.names()) == sorted([original, f"{original} (2)"])


def test_imported_profile_drops_broken_parts_instead_of_crashing(bot, tmp_path):
    path = tmp_path / "perfil.json"
    path.write_text(json.dumps({"format": "exordion-profile", "name": "Outro", "profile": {
        "fishing": {"rod": "x"}, "repeater": {"interval": 2.5},
        "loot": {"items": ["não é desenho"], "destination": [1, 2]},
    }}), encoding="utf-8")

    assert bot.import_profile(path)

    assert bot.profile_name == "Outro"
    assert bot.profile["fishing"]["rod"] is None
    assert bot.profile["repeater"]["interval"] == 2.5
    assert bot.profile["loot"]["items"] == [] and bot.profile["loot"]["destination"] == [1, 2]


@pytest.mark.parametrize("content", ["nada", "[]", '{"format": "exordion-loot", "profile": {}}',
                                     '{"format": "exordion-profile", "profile": []}'])
def test_file_that_is_not_a_profile_changes_nothing(bot, tmp_path, content):
    path = tmp_path / "perfil.json"
    path.write_text(content, encoding="utf-8")
    names = bot.store.names()
    assert not bot.import_profile(path)
    assert bot.store.names() == names


def test_rename_keeps_the_profile_and_remembers_it(bot):
    bot.profile["fishing"]["rod"] = [7, 8]
    original = bot.profile_name

    assert bot.rename_profile("  Druida  ")

    assert bot.profile_name == "Druida"
    assert bot.store.names() == ["Druida"]
    assert bot.store.load("Druida")["fishing"]["rod"] == [7, 8]
    assert bot.store.load_last()[0] == "Druida"
    assert original not in bot.store.names()


def test_rename_refuses_a_name_already_taken(bot):
    bot.store.save("Outro", {})
    assert not bot.rename_profile("Outro")
    assert "Outro" in bot.store.names() and bot.profile_name in bot.store.names()


def test_allowed_names_can_be_removed_one_by_one(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=1)
    bot.learn_visible_names()
    assert len(bot.profile["training"]["allowed_names"]) == 1

    bot.remove_name("allowed", 5)  # índice inválido não mexe na lista
    assert len(bot.profile["training"]["allowed_names"]) == 1

    bot.remove_name("allowed", 0)
    assert bot.profile["training"]["allowed_names"] == []
    assert ("names", None) in list(bot.events.queue)


def test_ignored_name_is_skipped_and_never_alarms(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=2)
    bot.learn_visible_names()
    assert len(bot.profile["training"]["allowed_names"]) == 2

    bot.set_name_ignored("allowed", 0, True)
    rows = bot.read_battle_list(bot.frames["frame"]).rows
    assert [(row.allowed, row.ignored) for row in rows] == [(False, True), (True, False)]
    assert bot.alarm.evaluate(bot.read_battle_list(bot.frames["frame"]), 0.0, True) is None

    bot.set_name_ignored("ignored", 0, False)
    assert len(bot.profile["training"]["ignored_names"]) == 0
    assert len(bot.profile["training"]["allowed_names"]) == 2


def test_summon_does_not_attack_when_only_one_mob_is_attackable(bot):
    bot.profile["training"]["region"] = [0, 0, 200, 240]
    bot.frames["frame"] = battle_frame(rows=2)
    bot.learn_visible_names()
    bot.set_name_ignored("allowed", 0, True)
    bot.set_module("training", True)

    bot.vision_tick(10.0)

    assert bot.am.calls == []


def test_normal_mode_heals_low_target_with_the_rune(bot):
    from src.battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState

    training = bot.profile["training"]
    training["mode"] = "normal"
    training["region"] = [0, 0, 200, 240]
    training["heal"].update(enabled=True, rune=[7, 8], below=30)
    row = BattleListRow(index=0, bounds=(0, 0, 100, 20), confidence=0.98, hp_state="red", hp_percent=20.0)
    snapshot = BattleListSnapshot((row,), SelectorState.VALID, True, 0.0, 0)
    bot.read_battle_list = lambda frame: snapshot
    bot.frames["frame"] = battle_frame(rows=1)
    bot.am.foreground = False
    bot.set_module("training", True)

    bot.vision_tick(10.0)
    assert bot.am.calls == []  # a leitura da tela não espera o mouse
    assert bot.run_next_action(timeout=0)

    assert bot.am.calls == [("right", (7, 8)), ("left", (50, 10))]


def test_a_busy_profile_file_does_not_break_the_hotkey(bot, monkeypatch):
    def busy(name, profile):
        raise PermissionError(32, "O arquivo já está sendo usado por outro processo")

    monkeypatch.setattr(bot.store, "save", busy)
    bot.profile["macros"]["f5"] = {"mode": "normal", "pos": [1, 2], "end": None}

    bot._toggle_module("macros")

    assert bot.macros_on
    assert any("Não consegui salvar" in message for message in drain_logs(bot))


def drain_logs(bot):
    messages = []
    while not bot.events.empty():
        kind, payload = bot.events.get_nowait()
        if kind == "log":
            messages.append(payload)
    return messages


class FakeCapture:
    made = []

    def __init__(self, am, count, timeout, on_point, on_done):
        self.on_done = on_done
        FakeCapture.made.append(self)

    def start(self):
        pass

    def cancel(self):
        pass


def test_a_replaced_capture_does_not_clear_the_new_one(bot, monkeypatch):
    FakeCapture.made = []
    monkeypatch.setattr("src.bot.ClickCapture", FakeCapture)
    bot.capture_rod()
    bot.capture_food()
    old, new = FakeCapture.made
    drain_logs(bot)

    old.on_done([[1, 1]])

    assert bot._click_capture is new
    assert bot.profile["fishing"]["rod"] is None
    new.on_done([[5, 5]])
    assert bot.profile["survival"]["eat"]["pos"] == [5, 5]
    assert bot._click_capture is None


def test_overlay_shows_what_is_on_and_what_has_a_hotkey(bot):
    bot.profile["module_hotkeys"].update(loot="f5", macros="shift+f1")
    bot.set_module("macros", True)

    state = bot.overlay_state()

    assert state["client"] == (100, 50, 800, 600)
    assert state["corner"] == "left"
    assert state["rows"] == [("Macros", "SHIFT+F1", True), ("Loot", "F5", False)]


def test_overlay_hides_when_the_game_is_behind_or_it_is_turned_off(bot):
    bot.profile["module_hotkeys"]["loot"] = "f5"
    bot.am.foreground = False
    assert bot.overlay_state() is None

    bot.am.foreground = True
    bot.profile["overlay"]["enabled"] = False
    assert bot.overlay_state() is None


def test_overlay_hides_when_there_is_nothing_to_show(bot):
    bot.profile["module_hotkeys"] = {name: "" for name in bot.profile["module_hotkeys"]}
    assert bot.overlay_state() is None


# ---------- fila com prioridade ----------

def test_heal_jumps_ahead_of_queued_macros(bot):
    done = []
    bot.queue_action("loot", "loot", lambda: done.append("loot"))
    bot.queue_action("macro", "f5", lambda: done.append("f5"))
    bot.queue_action("heal", "exura", lambda: done.append("exura"))

    while bot.run_next_action(timeout=0):
        pass

    assert done == ["exura", "f5", "loot"]


def test_survival_rule_goes_through_the_queue_as_heal(bot):
    rule = bot.profile["survival"]["rules"][0]
    rule.update(enabled=True, action="f5", percent=50)
    bot.survival_on = True
    bot.hp = 20.0

    bot.vision_tick(1.0)

    assert bot.am.calls == []
    level = bot._actions.queue[0][2]
    assert level == "heal"
    bot.run_next_action(timeout=0)
    assert bot.am.calls  # a macro f5 rodou


# ---------- captura rápida ----------

def fast_bot(bot, fast_frame):
    calls = {"grab": 0, "full": 0}
    full = np.full((100, 100, 3), 50, dtype=np.uint8)

    def grab(hwnd, areas, covering):
        calls["grab"] += 1
        return fast_frame

    def capture(hwnd):
        calls["full"] += 1
        return full

    bot._grab = grab
    bot._capture_frame = capture
    return calls, full


def test_fast_capture_is_checked_once_against_the_full_one(bot):
    fast = np.zeros((100, 100, 3), dtype=np.uint8)
    fast[10:20, 10:30] = 50
    calls, full = fast_bot(bot, fast)

    assert bot._game_frame([(10, 10, 20, 10)]) is full  # primeira vez: confere
    assert bot._game_frame([(10, 10, 20, 10)]) is fast
    assert calls == {"grab": 2, "full": 1}


def test_fast_capture_that_differs_from_the_game_is_turned_off(bot):
    calls, full = fast_bot(bot, np.zeros((100, 100, 3), dtype=np.uint8))  # escala de tela, por exemplo

    bot._game_frame([(10, 10, 20, 10)])
    assert bot._game_frame([(10, 10, 20, 10)]) is full

    assert calls == {"grab": 1, "full": 2}


def test_without_areas_the_full_capture_is_used(bot):
    calls, full = fast_bot(bot, np.zeros((100, 100, 3), dtype=np.uint8))
    assert bot._game_frame() is full
    assert calls["grab"] == 0


# ---------- Testar input ----------

def input_test_bot(bot, monkeypatch, moves_by):
    from PIL import Image
    from pathlib import Path
    from src import loot
    sample = np.asarray(Image.open(Path(__file__).parent / "assets" / "loot_backpack.png").convert("RGB"))
    moved = sample.copy()
    moved[25:57, 14:46] = sample[25:57, 88:120]  # o item saiu do primeiro slot
    bot.profile["loot"]["grid"] = [14, 25, 4, 1]
    bot.profile["input"]["server_wait"] = 0.05
    bot.frames["frame"] = sample
    monkeypatch.setattr("src.bot.time.sleep", lambda _s: None)
    am = bot.am

    def drag(start, end, quick=False):
        am.calls.append(("drag", start, end))
        if "message" in moves_by:
            bot.frames["frame"] = moved

    def drag_with_cursor(start, end, quick=False):
        am.calls.append(("drag_cursor", start, end))
        if "cursor" in moves_by:
            bot.frames["frame"] = moved

    am.drag, am.drag_with_cursor = drag, drag_with_cursor
    bot._run_input_test()
    return [call[0] for call in am.calls]


def test_input_test_switches_to_messages_when_they_work(bot, monkeypatch):
    calls = input_test_bot(bot, monkeypatch, moves_by={"message", "cursor"})
    assert calls == ["drag"]
    assert bot.profile["input"]["mode"] == "message"
    assert bot.store.load(bot.profile_name)["input"]["mode"] == "message"


def test_input_test_keeps_auto_when_only_the_cursor_works(bot, monkeypatch):
    bot.profile["input"]["mode"] = "message"
    calls = input_test_bot(bot, monkeypatch, moves_by={"cursor"})
    assert calls == ["drag", "drag_cursor"]
    assert bot.profile["input"]["mode"] == "auto"


def test_input_test_says_so_when_nothing_moves(bot, monkeypatch):
    input_test_bot(bot, monkeypatch, moves_by=set())
    assert any("não se mexeu de nenhum jeito" in message for message in drain_logs(bot))
