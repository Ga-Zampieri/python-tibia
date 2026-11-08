from pynput.keyboard import Key, KeyCode

from src.hotkey_service import HotkeyService, combo_name, key_name


def service():
    seen = []
    return HotkeyService(lambda name, mods, repeat: seen.append((name, mods, repeat))), seen


def test_combo_order_does_not_depend_on_press_order():
    assert combo_name("f1", {"shift", "ctrl"}) == "ctrl+shift+f1"
    assert combo_name("f1") == "f1"


def test_key_name_recovers_letter_and_digit_under_ctrl():
    assert key_name(KeyCode(vk=0x41, char="\x01")) == "a"
    assert key_name(KeyCode(vk=0x31)) == "1"
    assert key_name(KeyCode(vk=0x41, char="A")) == "a"
    assert key_name(Key.f5) == "f5"


def test_modifiers_are_reported_with_the_key_and_never_alone():
    hotkeys, seen = service()
    hotkeys._on_press(Key.ctrl_l)
    hotkeys._on_press(Key.alt_l)
    hotkeys._on_press(Key.f2)
    assert seen == [("f2", {"ctrl", "alt"}, False)]


def test_releasing_one_shift_keeps_the_other():
    hotkeys, seen = service()
    hotkeys._on_press(Key.shift_l)
    hotkeys._on_press(Key.shift_r)
    hotkeys._on_release(Key.shift_l)
    hotkeys._on_press(Key.f1)
    assert seen == [("f1", {"shift"}, False)]


def test_auto_repeat_is_flagged_until_release():
    hotkeys, seen = service()
    hotkeys._on_press(Key.f5)
    hotkeys._on_press(Key.f5)
    hotkeys._on_release(Key.f5)
    hotkeys._on_press(Key.f5)
    assert [repeat for _, _, repeat in seen] == [False, True, False]


def test_letter_released_after_shift_is_not_stuck_as_held():
    hotkeys, seen = service()
    hotkeys._on_press(Key.shift)
    hotkeys._on_press(KeyCode(vk=0x41, char="A"))
    hotkeys._on_release(Key.shift)
    hotkeys._on_release(KeyCode(vk=0x41, char="a"))
    hotkeys._on_press(Key.shift)
    hotkeys._on_press(KeyCode(vk=0x41, char="A"))
    assert seen == [("a", {"shift"}, False), ("a", {"shift"}, False)]


def test_unknown_key_is_ignored():
    hotkeys, seen = service()
    hotkeys._on_press(KeyCode(vk=0xFF))
    assert seen == []
