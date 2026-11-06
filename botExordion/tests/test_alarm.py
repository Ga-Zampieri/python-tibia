from src.alarm import AlarmMonitor
from src.battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState


def snapshot(*allowed):
    rows = tuple(
        BattleListRow(index=i, bounds=(0, i, 1, i + 1), confidence=0.98, allowed=flag)
        for i, flag in enumerate(allowed)
    )
    return BattleListSnapshot(rows, SelectorState.VALID, True, 0.0)


def test_without_names_alarm_fires_when_list_grows():
    alarm = AlarmMonitor()
    assert alarm.evaluate(snapshot(True), 0, False) is None
    assert alarm.evaluate(snapshot(True), 1, False) is None
    assert "1 para 2" in alarm.evaluate(snapshot(True, True), 2, False)


def test_with_names_only_unknown_rows_fire():
    alarm = AlarmMonitor()
    assert alarm.evaluate(snapshot(True, True, True), 0, True) is None
    assert "1 nome" in alarm.evaluate(snapshot(True, False), 1, True)


def test_alarm_repeats_only_after_cooldown():
    alarm = AlarmMonitor(cooldown=10)
    alarm.evaluate(snapshot(), 0, False)
    assert alarm.evaluate(snapshot(True), 1, False)
    assert alarm.evaluate(snapshot(True), 5, False) is None
    assert alarm.evaluate(snapshot(True), 12, False)


def test_reset_takes_a_new_baseline():
    alarm = AlarmMonitor()
    alarm.evaluate(snapshot(), 0, False)
    alarm.reset()
    assert alarm.evaluate(snapshot(True, True), 1, False) is None
