from src.battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState
from src.training import (AttackPlanner, HealPlanner, NormalOrder, TrainingMode, TrainingState,
                          TrainingStateMachine)


def _snapshot(rows, selected=None):
    return BattleListSnapshot(
        rows=tuple(rows),
        state=SelectorState.VALID,
        complete=True,
        captured_at=0,
        selected_index=selected,
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


def test_summon_mode_needs_two_attackable_mobs():
    """Ignorado não conta: sobrando um atacável, ele é o bicho principal (ex.: a slime mãe)."""
    planner = AttackPlanner(TrainingStateMachine())
    pos, reason = planner.plan(_snapshot((_row(0, allowed=False), _row(1))), 0.0)
    assert pos is None
    assert "principal" in reason


def test_summon_mode_skips_ignored_rows_from_the_top():
    planner = AttackPlanner(TrainingStateMachine())
    snapshot = _snapshot((_row(0, allowed=False), _row(1), _row(2)))
    pos, reason = planner.plan(snapshot, 0.0)
    assert pos == (50, 30)
    assert reason == "Atacando alvo #1."


def test_summon_mode_keeps_current_target_until_it_dies():
    planner = AttackPlanner(TrainingStateMachine())
    snapshot = _snapshot((_row(0), _row(1), _row(2)), selected=2)
    assert planner.plan(snapshot, 0.0)[0] is None


def test_planner_clicks_row_center_and_respects_cooldown():
    planner = AttackPlanner(TrainingStateMachine())
    snapshot = _snapshot((_row(0), _row(1)))
    assert planner.plan(snapshot, 10.0)[0] == (50, 10)
    assert planner.plan(snapshot, 10.5)[0] is None
    assert planner.plan(snapshot, 11.5)[0] == (50, 10)


def test_normal_mode_keeps_attacking_selected_target_even_if_name_changed():
    """Log real: o alvo #0 (nome vermelho) deixava de bater e o bot alternava
    #0 -> #1 -> #0 a cada leitura, ligando e desligando o ataque."""
    planner = AttackPlanner(TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES))
    snapshot = _snapshot((_row(0, allowed=False), _row(1, hp="yellow")), selected=0)

    for now in (10.0, 11.6, 13.2):
        pos, reason = planner.plan(snapshot, now)
        assert pos is None
        assert reason == "Alvo já selecionado."


def _hp_row(index, percent, allowed=True):
    state = "green" if percent >= 60 else "yellow" if percent >= 30 else "red"
    return BattleListRow(index=index, bounds=(0, index * 20, 100, index * 20 + 20), confidence=0.98,
                         hp_state=state, allowed=allowed, hp_percent=percent)


def test_normal_mode_switches_to_the_mob_with_more_life():
    """Print real: alvo #0 com 29,8% e #1 com 33,1%; tem que ir para o #1."""
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 29.8), _hp_row(1, 33.1)), selected=0)
    assert machine.get_next_target(snapshot) == 1


def test_normal_mode_does_not_switch_for_a_tiny_difference():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 30.0), _hp_row(1, 31.5)), selected=0)
    assert machine.get_next_target(snapshot) == 0


def test_normal_mode_keeps_target_while_it_has_enough_life():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 55.0), _hp_row(1, 100.0)), selected=0)
    assert machine.get_next_target(snapshot) == 0


def test_normal_mode_picks_the_healthiest_allowed_mob_to_start():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 40.0), _hp_row(1, 100.0, allowed=False), _hp_row(2, 80.0)))
    assert machine.get_next_target(snapshot) == 2


def test_normal_mode_finishes_the_last_mob():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 5.0),), selected=0)
    assert machine.get_next_target(snapshot) == 0



def test_normal_top_order_attacks_first_allowed_and_stays_until_death():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES, normal_order=NormalOrder.TOP)
    assert machine.get_next_target(_snapshot((_hp_row(0, 90, allowed=False), _hp_row(1, 20),
                                              _hp_row(2, 100)))) == 1
    # Com o alvo fraco e outro cheio, no modo topo ele não troca.
    assert machine.get_next_target(_snapshot((_hp_row(0, 5), _hp_row(1, 100)), selected=0)) == 0


def test_normal_mode_skips_ignored_names_when_balancing():
    machine = TrainingStateMachine(mode=TrainingMode.NORMAL_CREATURES)
    snapshot = _snapshot((_hp_row(0, 20), _hp_row(1, 100, allowed=False), _hp_row(2, 60)), selected=0)
    assert machine.get_next_target(snapshot) == 2


HEAL = {"enabled": True, "rune": [10, 20], "below": 30, "cooldown": 2.0}


def test_heal_uses_rune_on_target_below_limit_respecting_cooldown():
    healer = HealPlanner()
    snapshot = _snapshot((_hp_row(0, 25), _hp_row(1, 10)), selected=0)

    pos, reason = healer.plan(snapshot, 10.0, HEAL)
    assert pos == (50, 10)
    assert reason == "Curando alvo #0 (HP 25%)."
    assert healer.plan(snapshot, 11.0, HEAL)[0] is None  # intervalo
    assert healer.plan(snapshot, 12.0, HEAL)[0] == (50, 10)


def test_heal_waits_for_low_life_target_and_configuration():
    healer = HealPlanner()
    assert healer.plan(_snapshot((_hp_row(0, 80),), selected=0), 0.0, HEAL)[0] is None
    assert healer.plan(_snapshot((_hp_row(0, 10),)), 0.0, HEAL)[0] is None  # sem alvo
    assert healer.plan(_snapshot((_hp_row(0, 10),), selected=0), 0.0, dict(HEAL, rune=None))[0] is None
    assert healer.plan(_snapshot((_hp_row(0, 10),), selected=0), 0.0, dict(HEAL, enabled=False))[0] is None
