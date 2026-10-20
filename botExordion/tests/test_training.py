from src.battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState
from src.training import TrainingStateMachine, TrainingState


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
