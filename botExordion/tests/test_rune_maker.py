import copy

import numpy as np

from conftest import FakeActionManager
from src.rune_maker import RuneMaker
from src.settings import DEFAULT_PROFILE


def make(mana=None, am=None):
    config = copy.deepcopy(DEFAULT_PROFILE["rune_maker"])
    config.update(blank=[1, 1], hand=[2, 2], output=[3, 3], spell="adura vita", cast_wait=0.2)
    maker = RuneMaker(config, lambda: mana)
    maker.am = am or FakeActionManager(foreground=False)
    maker._stop_event.wait = lambda _seconds: False
    return maker


def test_cycle_moves_blank_casts_and_stores_rune():
    maker = make()

    assert maker.cycle() is True
    assert maker.am.calls == [
        ("drag", (1, 1), (2, 2)),
        ("text", "adura vita"),
        ("drag", (2, 2), (3, 3)),
    ]
    assert maker.am.block_calls == 2
    assert maker.casts == 1


def test_cycle_stops_without_input_block():
    maker = make(am=FakeActionManager(block_ok=False))

    assert maker.cycle() is False
    assert maker.am.calls == []


def test_mana_gate():
    assert make(mana=50).has_mana() is False
    assert make(mana=85).has_mana() is True
    assert make(mana=None).has_mana() is True


def test_reports_what_is_missing():
    maker = make()
    maker.config["spell"] = ""
    assert maker.missing() == "magia"
    assert maker.start() is False


def hand_frame(sprite=None):
    frame = np.zeros((60, 60, 3), dtype=np.uint8)
    if sprite is not None:
        frame[24:36, 24:36] = sprite
    return frame


BLANK = (200, 200, 200)
FOOD = (180, 40, 40)


def with_frames(frames):
    """Cada leitura consome um frame; o último se repete."""
    maker = make()
    maker.config["hand"] = [30, 30]
    maker.alerts = []
    maker.alert = maker.alerts.append
    queue = list(frames)
    maker.get_frame = lambda: queue.pop(0) if len(queue) > 1 else queue[0]
    return maker


def cast(maker):
    return [call for call in maker.am.calls if call[0] == "text"]


def test_blank_reaches_hand_and_rune_is_made():
    maker = with_frames([hand_frame(), hand_frame(BLANK)])

    assert maker.cycle() is True
    assert maker.casts == 1 and maker.alerts == []


def test_slow_server_gets_time_to_move_the_blank():
    maker = with_frames([hand_frame(), hand_frame(), hand_frame(), hand_frame(BLANK)])

    assert maker.cycle() is True
    assert maker.alerts == []


def test_stops_and_warns_when_blanks_run_out():
    maker = with_frames([hand_frame()])

    assert maker.cycle() is False
    assert cast(maker) == []
    assert maker.casts == 0
    assert len(maker.alerts) == 1
    assert maker._stop_event.is_set()


def test_stops_when_another_item_slides_into_the_blank_slot():
    maker = with_frames([hand_frame(), hand_frame(BLANK), hand_frame(), hand_frame(FOOD)])

    assert maker.cycle() is True
    assert maker.cycle() is False
    assert len(cast(maker)) == 1
    assert maker.casts == 1
    assert "outro item" in maker.alerts[0]


def test_each_run_learns_the_blank_again():
    maker = with_frames([hand_frame(), hand_frame(BLANK)])
    maker.cycle()
    maker._stop_event.wait = lambda _seconds: True

    assert maker.start() is True
    maker.stop()

    assert maker._blank_sprite is None


def test_without_image_the_cycle_goes_on_and_warns_once():
    maker = make()
    logs = []
    maker.log = logs.append

    assert maker.cycle() is True
    assert maker.cycle() is True
    assert maker.casts == 2
    assert len(logs) == 1


def test_stopping_while_waiting_for_the_blank_does_not_alert():
    maker = with_frames([hand_frame()])
    answers = iter([False, True])
    maker._stop_event.wait = lambda _seconds: next(answers)

    assert maker.cycle() is False
    assert maker.alerts == []


def test_game_in_front_moves_runes_with_the_real_cursor():
    maker = make(am=FakeActionManager(foreground=True))

    assert maker.cycle() is True

    assert [call[0] for call in maker.am.calls] == ["drag_cursor", "text", "drag_cursor"]
