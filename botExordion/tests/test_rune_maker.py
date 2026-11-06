import copy

from conftest import FakeActionManager
from src.rune_maker import RuneMaker
from src.settings import DEFAULT_PROFILE


def make(mana=None, am=None):
    config = copy.deepcopy(DEFAULT_PROFILE["rune_maker"])
    config.update(blank=[1, 1], hand=[2, 2], output=[3, 3], spell="adura vita", cast_wait=0.2)
    maker = RuneMaker(config, lambda: mana)
    maker.am = am or FakeActionManager()
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
