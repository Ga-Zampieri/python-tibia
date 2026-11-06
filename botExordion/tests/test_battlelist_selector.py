from src.battle_list_selector import (
    BattleListRegion,
    BattleListRegionValidator,
    BattleListRow,
    BattleListSnapshot,
    SafeBattleListTargetSelector,
    SelectorState,
)
from src.training import TrainingStateMachine


def test_protected_last_row_is_blocked():
    selector = SafeBattleListTargetSelector(min_confidence=0.8)
    snapshot = BattleListSnapshot(
        rows=(
            BattleListRow(index=0, bounds=(0, 0, 200, 20), confidence=0.99),
            BattleListRow(index=1, bounds=(0, 20, 200, 40), confidence=0.99),
            BattleListRow(index=2, bounds=(0, 40, 200, 60), confidence=0.99),
        ),
        state=SelectorState.VALID,
        complete=True,
        captured_at=1.0,
    )
    assert selector.get_protected_index(snapshot) == 2
    assert selector.is_candidate_eligible(snapshot, 1) is True
    assert selector.is_candidate_eligible(snapshot, 2) is False


def test_incomplete_snapshot_is_blocked():
    selector = SafeBattleListTargetSelector(min_confidence=0.8)
    snapshot = BattleListSnapshot(
        rows=(BattleListRow(index=0, bounds=(0, 0, 200, 20), confidence=0.99),),
        state=SelectorState.UNCERTAIN,
        complete=False,
        captured_at=1.0,
    )
    assert selector.validate_snapshot(snapshot) is False
    assert selector.is_candidate_eligible(snapshot, 0) is False


def test_two_consistent_snapshots_resume_validation():
    selector = SafeBattleListTargetSelector(min_confidence=0.8, required_stable_captures=2)
    row_a = BattleListRow(index=0, bounds=(0, 0, 200, 20), confidence=0.99)
    row_b = BattleListRow(index=1, bounds=(0, 20, 200, 40), confidence=0.99)
    row_c = BattleListRow(index=2, bounds=(0, 40, 200, 60), confidence=0.99)

    first = BattleListSnapshot((row_a, row_b, row_c), SelectorState.VALID, True, 1.0)
    second = BattleListSnapshot((row_a, row_b, row_c), SelectorState.VALID, True, 1.1)

    assert selector.validate_snapshot(first) is False
    assert selector.validate_snapshot(second) is True


def test_training_machine_selects_safe_target_only():
    machine = TrainingStateMachine()
    rows = (
        BattleListRow(index=0, bounds=(0, 0, 200, 20), confidence=0.99),
        BattleListRow(index=1, bounds=(0, 20, 200, 40), confidence=0.99),
        BattleListRow(index=2, bounds=(0, 40, 200, 60), confidence=0.99),
    )
    snapshot = BattleListSnapshot(rows=rows, state=SelectorState.VALID, complete=True, captured_at=2.0)

    assert machine.selector.validate_snapshot(snapshot) is False
    assert machine.selector.validate_snapshot(snapshot) is True
    assert machine.get_next_target(snapshot) in (0, 1)
    assert machine.get_next_target(snapshot) != 2


def test_battle_list_region_validator_accepts_valid_screen_region():
    region = BattleListRegion(left=100, top=200, width=260, height=180, monitor=1)
    validator = BattleListRegionValidator(screen_size=(1920, 1080))

    assert validator.is_valid(region) is True
    assert validator.is_valid(BattleListRegion(left=0, top=0, width=10, height=10, monitor=1)) is False


def test_battle_list_region_validator_rejects_out_of_bounds_region():
    region = BattleListRegion(left=1900, top=1000, width=80, height=120, monitor=1)
    validator = BattleListRegionValidator(screen_size=(1920, 1080))

    assert validator.is_valid(region) is False


def test_region_builds_snapshot_with_first_target_only_when_two_or_more_rows_exist():
    region = BattleListRegion(left=100, top=200, width=300, height=180, monitor=1)
    snapshot = SafeBattleListTargetSelector().get_eligible_targets(
        BattleListSnapshot(
            rows=(
                BattleListRow(index=0, bounds=(100, 200, 400, 260), confidence=0.99),
                BattleListRow(index=1, bounds=(100, 260, 400, 320), confidence=0.99),
                BattleListRow(index=2, bounds=(100, 320, 400, 380), confidence=0.99),
            ),
            state=SelectorState.VALID,
            complete=True,
            captured_at=1.0,
        )
    )

    assert snapshot[:2] == (0, 1)
    assert snapshot[0] == 0
    assert len(snapshot) >= 2
