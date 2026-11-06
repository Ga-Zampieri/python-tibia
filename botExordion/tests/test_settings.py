import json

from src.settings import DEFAULT_NAME, DEFAULT_PROFILE, ProfileStore, import_legacy_mappings, merge_defaults


def test_first_run_imports_old_mappings(tmp_path):
    legacy = tmp_path / "runa_mappings.json"
    legacy.write_text(json.dumps({
        "player_position": [871, 478],
        "mappings": {
            "f9": {"rune": [1768, 508], "self_use": False, "push_item": False, "drag_end": None},
            "m": {"rune": [1772, 640], "self_use": True, "push_item": False, "drag_end": None},
            "f1": {"rune": [1, 2], "self_use": False, "push_item": True, "drag_end": [3, 4]},
        },
    }), encoding="utf-8")

    name, profile = ProfileStore(tmp_path / "cfg", legacy).load_last()

    assert name == DEFAULT_NAME
    assert profile["legacy_screen_coords"] is True
    assert profile["player_position"] == [871, 478]
    assert profile["macros"]["f9"] == {"mode": "normal", "pos": [1768, 508], "end": None}
    assert profile["macros"]["m"]["mode"] == "self"
    assert profile["macros"]["f1"] == {"mode": "drag", "pos": [1, 2], "end": [3, 4]}


def test_oldest_format_with_player_per_hotkey_is_migrated():
    profile = import_legacy_mappings({"f5": {"rune": [10, 20], "player": [30, 40], "self_use": True}})
    assert profile["player_position"] == [30, 40]

    assert import_legacy_mappings({"f5": [10, 20]})["macros"]["f5"]["mode"] == "normal"


def test_profile_round_trip_and_last_used(tmp_path):
    store = ProfileStore(tmp_path, tmp_path / "missing.json")
    profile = store.load("Knight")
    profile["fishing"]["rod"] = [1, 2]
    store.save("Knight", profile)
    store.save("Druid", store.load("Druid"))
    store.remember_last("Knight")

    name, loaded = ProfileStore(tmp_path, tmp_path / "missing.json").load_last()

    assert name == "Knight"
    assert loaded["fishing"]["rod"] == [1, 2]


def test_new_settings_reach_old_profiles():
    merged = merge_defaults(DEFAULT_PROFILE, {"survival": {"eat": {"interval": 60}}})
    assert merged["survival"]["eat"] == {"enabled": False, "pos": None, "interval": 60}
    assert merged["rune_maker"]["mana_percent"] == 80


def test_macros_are_not_mixed_with_defaults():
    merged = merge_defaults(DEFAULT_PROFILE, {"macros": {"f5": {"mode": "normal", "pos": [1, 2], "end": None}}})
    assert list(merged["macros"]) == ["f5"]


def test_corrupted_profile_is_set_aside(tmp_path):
    store = ProfileStore(tmp_path, tmp_path / "missing.json")
    (store.dir / "Bad.json").write_text("{quebrado", encoding="utf-8")

    assert store.load("Bad")["macros"] == {}
    assert (store.dir / "Bad.bad").exists()
