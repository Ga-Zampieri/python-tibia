import copy

from conftest import FakeActionManager
from src.settings import DEFAULT_PROFILE
from src.survival import Survival


def make():
    config = copy.deepcopy(DEFAULT_PROFILE["survival"])
    actions = []
    survival = Survival(config, actions.append)
    survival.am = FakeActionManager()
    return survival, config, actions


def test_eats_on_start_then_by_interval():
    survival, config, _ = make()
    config["eat"].update(enabled=True, pos=[5, 6], interval=60)

    survival.tick(100, None, None)
    survival.tick(120, None, None)
    survival.tick(161, None, None)

    assert survival.am.calls == [("right", (5, 6)), ("right", (5, 6))]


def test_anti_idle_waits_one_interval_and_alternates_direction():
    survival, config, _ = make()
    config["anti_idle"].update(enabled=True, interval=60)

    survival.tick(0, None, None)
    survival.tick(61, None, None)
    survival.tick(122, None, None)

    assert survival.am.calls == [("turn", "up"), ("turn", "down")]


def test_rule_fires_below_threshold_respecting_cooldown():
    survival, config, actions = make()
    config["rules"][0].update(enabled=True, percent=50, action="f1", cooldown=2)

    survival.tick(0, 80, None)
    survival.tick(1, 40, None)
    survival.tick(2, 40, None)
    survival.tick(3.5, 40, None)

    assert actions == ["f1", "f1"]


def test_mana_rule_fires_above_threshold():
    survival, config, actions = make()
    config["rules"][2].update(enabled=True, percent=90, action="utevo lux")

    survival.tick(0, None, 50)
    survival.tick(1, None, 95)

    assert actions == ["utevo lux"]


def test_unreadable_bar_never_triggers_a_rule():
    survival, config, actions = make()
    config["rules"][0].update(enabled=True, percent=50, action="f1")

    survival.tick(0, None, None)

    assert actions == []
