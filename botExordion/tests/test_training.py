from src.battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState
from src.training import AttackPlanner, TrainingMode, TrainingState, TrainingStateMachine


def _snapshot(rows):
    return BattleListSnapshot(
        rows=tuple(rows),
        state=SelectorState.VALID,
        complete=True,
        captured_at=0,
    )


def test_training_machine_transitions():
    machine = TrainingStateMachine()
    assert machine.state == TrainingState.INATIVO
    machine.start()
    assert machine.state == TrainingState.CALIBRANDO
    machine.identify_target()
    assert machine.state == TrainingState.IDENTIFICANDO_ALVO
    machine.train()
    assert machine.state == TrainingState.TREINANDO


def test_training_requires_two_targets_before_attack():
    machine = TrainingStateMachine()
    rows = (
        BattleListRow(index=0, bounds=(0, 0, 50, 20), confidence=0.99),
        BattleListRow(index=1, bounds=(0, 25, 50, 45), confidence=0.99),
        BattleListRow(index=2, bounds=(0, 50, 50, 70), confidence=0.99),
    )
    snapshot = _snapshot(rows)
    machine.selector.validate_snapshot(snapshot)
    machine.selector.validate_snapshot(snapshot)

    decision = machine.evaluate_battle_list(snapshot)

    assert decision.can_attack is True
    assert decision.eligible_targets[0] == 0
    assert machine.get_next_target(snapshot) == 0

    short_snapshot = _snapshot(rows[:1])
    machine.selector.validate_snapshot(short_snapshot)
    machine.selector.validate_snapshot(short_snapshot)

    short_decision = machine.evaluate_battle_list(short_snapshot)

    assert short_decision.can_attack is False
    assert machine.get_next_target(short_snapshot) is None


def _row(index, hp="green", allowed=True):
    return BattleListRow(index=index, bounds=(0, index * 20, 100, index * 20 + 20),
                         confidence=0.98, hp_state=hp, allowed=allowed)


def test_normal_mode_skips_rows_outside_allowed_names():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    assert machine.get_next_target(_snapshot((_row(0, allowed=False), _row(1)))) == 1


def test_normal_mode_with_only_unknown_rows_has_no_target():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    assert machine.get_next_target(_snapshot((_row(0, allowed=False),))) is None


def test_summon_mode_refuses_unknown_first_row():
    planner = AttackPlanner(TrainingStateMachine())
    pos, reason = planner.plan(_snapshot((_row(0, allowed=False), _row(1))), 0.0)
    assert pos is None
    assert "permitidos" in reason


def test_planner_clicks_row_center_and_respects_cooldown():
    planner = AttackPlanner(TrainingStateMachine())
    snapshot = _snapshot((_row(0), _row(1)))
    assert planner.plan(snapshot, 10.0)[0] == (50, 10)
    assert planner.plan(snapshot, 10.5)[0] is None
    assert planner.plan(snapshot, 11.5)[0] == (50, 10)
