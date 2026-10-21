import json

import pytest

from src.macro_rune import Runa


def test_default_rune_click_restores_cursor(monkeypatch):
    runa = Runa(None)
    runa._mappings["f5"] = (10, 20)
    calls = []
    block_calls = []
    monkeypatch.setattr(Runa, "_set_user_input_blocked", staticmethod(lambda blocked: block_calls.append(blocked) or True))
    monkeypatch.setattr(Runa, "_get_cursor_pos", staticmethod(lambda: (3, 4)))
    monkeypatch.setattr(Runa, "_set_cursor_pos", staticmethod(lambda x, y: calls.append(("move", x, y)) or True))
    monkeypatch.setattr(Runa, "_send_right_click", staticmethod(lambda: calls.append(("right",))))
    monkeypatch.setattr(Runa, "_send_left_click", staticmethod(lambda: calls.append(("left",))))
    monkeypatch.setattr("src.macro_rune.sleep", lambda duration: None)

    assert runa.equipRuna("f5") is True
    assert calls == [("move", 10, 20), ("right",), ("move", 3, 4)]
    assert block_calls == [True, False]


def test_self_use_clicks_rune_then_player_and_restores_cursor(monkeypatch):
    runa = Runa(None)
    runa._mappings["f5"] = (10, 20)
    runa._player_position = (30, 40)
    runa._self_use_mappings["f5"] = True
    calls = []
    block_calls = []
    monkeypatch.setattr(Runa, "_set_user_input_blocked", staticmethod(lambda blocked: block_calls.append(blocked) or True))
    monkeypatch.setattr(Runa, "_get_cursor_pos", staticmethod(lambda: (3, 4)))
    monkeypatch.setattr(Runa, "_set_cursor_pos", staticmethod(lambda x, y: calls.append(("move", x, y)) or True))
    monkeypatch.setattr(Runa, "_send_right_click", staticmethod(lambda: calls.append(("right",))))
    monkeypatch.setattr(Runa, "_send_left_click", staticmethod(lambda: calls.append(("left",))))
    monkeypatch.setattr("src.macro_rune.sleep", lambda duration: None)

    assert runa.equipRuna("f5") is True
    assert calls == [
        ("move", 10, 20),
        ("right",),
        ("move", 30, 40),
        ("left",),
        ("move", 3, 4),
    ]
    assert block_calls == [True, False]


def test_failed_input_block_cancels_rune_action(monkeypatch):
    runa = Runa(None)
    runa._mappings["f5"] = (10, 20)
    calls = []
    monkeypatch.setattr(Runa, "_set_user_input_blocked", staticmethod(lambda blocked: calls.append(blocked) or False))
    monkeypatch.setattr(Runa, "_get_cursor_pos", staticmethod(lambda: pytest.fail("cursor should not be read")))

    assert runa.equipRuna("f5") is False
    assert calls == [True]


def test_input_is_unblocked_after_action_error(monkeypatch):
    runa = Runa(None)
    runa._mappings["f5"] = (10, 20)
    block_calls = []
    cursor_calls = []
    monkeypatch.setattr(Runa, "_set_user_input_blocked", staticmethod(lambda blocked: block_calls.append(blocked) or True))
    monkeypatch.setattr(Runa, "_get_cursor_pos", staticmethod(lambda: (3, 4)))

    def move_cursor(x, y):
        cursor_calls.append((x, y))
        if (x, y) == (10, 20):
            raise RuntimeError("simulated move failure")
        return True

    monkeypatch.setattr(Runa, "_set_cursor_pos", staticmethod(move_cursor))

    assert runa.equipRuna("f5") is False
    assert block_calls == [True, False]
    assert cursor_calls == [(10, 20), (3, 4)]


def test_load_legacy_mapping_defaults_to_normal_mode(tmp_path):
    mappings_file = tmp_path / "mappings.json"
    mappings_file.write_text(json.dumps({"f5": [10, 20]}), encoding="utf-8")
    runa = Runa(None)
    runa._mappings_file = str(mappings_file)

    assert runa.load_mappings() is True
    assert runa._mappings == {"f5": (10, 20)}
    assert runa.is_self_use_enabled("f5") is False


def test_save_and_load_self_use_mapping(tmp_path):
    mappings_file = tmp_path / "mappings.json"
    runa = Runa(None)
    runa._mappings_file = str(mappings_file)
    runa._mappings["f5"] = (10, 20)
    runa._player_position = (30, 40)
    runa.set_self_use("f5", True)

    assert runa.save_mappings() is True

    loaded = Runa(None)
    loaded._mappings_file = str(mappings_file)
    assert loaded.load_mappings() is True
    assert loaded._mappings == {"f5": (10, 20)}
    assert loaded._player_position == (30, 40)
    assert loaded.is_self_use_enabled("f5") is True


def test_player_position_is_shared_by_all_self_use_hotkeys(monkeypatch):
    runa = Runa(None)
    runa._mappings = {"f5": (10, 20), "f6": (11, 21)}
    runa._self_use_mappings = {"f5": True, "f6": True}
    runa._player_position = (30, 40)
    player_clicks = []
    monkeypatch.setattr(Runa, "_set_user_input_blocked", staticmethod(lambda blocked: True))
    monkeypatch.setattr(Runa, "_get_cursor_pos", staticmethod(lambda: (3, 4)))
    monkeypatch.setattr(Runa, "_set_cursor_pos", staticmethod(lambda x, y: player_clicks.append((x, y)) or True))
    monkeypatch.setattr(Runa, "_send_right_click", staticmethod(lambda: None))
    monkeypatch.setattr(Runa, "_send_left_click", staticmethod(lambda: None))
    monkeypatch.setattr("src.macro_rune.sleep", lambda duration: None)

    assert runa.equipRuna("f5") is True
    assert runa.equipRuna("f6") is True
    assert player_clicks.count((30, 40)) == 2


def test_legacy_per_hotkey_player_position_is_migrated(tmp_path):
    mappings_file = tmp_path / "mappings.json"
    mappings_file.write_text(
        json.dumps({"f5": {"rune": [10, 20], "player": [30, 40], "self_use": True}}),
        encoding="utf-8",
    )
    runa = Runa(None)
    runa._mappings_file = str(mappings_file)

    assert runa.load_mappings() is True
    assert runa._player_position == (30, 40)


def test_loading_for_player_capture_preserves_unsaved_mappings(tmp_path):
    mappings_file = tmp_path / "mappings.json"
    mappings_file.write_text(
        json.dumps({"f5": {"rune": [10, 20], "self_use": True}}),
        encoding="utf-8",
    )
    runa = Runa(None)
    runa._mappings_file = str(mappings_file)
    runa._mappings["f6"] = (50, 60)
    runa.set_self_use("f6", False)

    assert runa.load_mappings(merge_existing=True) is True
    assert runa._mappings == {"f5": (10, 20), "f6": (50, 60)}
    assert runa.is_self_use_enabled("f5") is True
    assert runa.is_self_use_enabled("f6") is False