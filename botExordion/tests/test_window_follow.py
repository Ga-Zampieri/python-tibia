from src.window_follow import follow_step
from src.ui import natural_key


def test_game_that_moves_takes_the_bot_along():
    target, offset = follow_step((300, 200), (100, 100), (1100, 100), [1000, 0])
    assert target == (1300, 200)
    assert offset == [1000, 0]


def test_bot_dragged_by_the_person_sets_a_new_distance():
    target, offset = follow_step((100, 100), (100, 100), (900, 150), [1000, 0])
    assert target is None
    assert offset == [800, 50]


def test_game_that_just_appeared_brings_the_bot_to_the_saved_place():
    target, offset = follow_step((100, 100), None, (5, 5), [1000, 0])
    assert target == (1100, 100)


def test_first_time_keeps_the_bot_where_it_is():
    target, offset = follow_step((100, 100), None, (40, 60), None)
    assert target is None
    assert offset == [-60, -40]


def test_bot_already_in_place_is_not_moved_again():
    target, _ = follow_step((300, 200), (100, 100), (1300, 200), [1000, 0])
    assert target is None


def test_hotkeys_are_listed_in_number_order():
    keys = ["f10", "f2", "f1", "m", "f11"]
    assert sorted(keys, key=natural_key) == ["f1", "f2", "f10", "f11", "m"]
