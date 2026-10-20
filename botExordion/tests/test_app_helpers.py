import app


class DummyActionManager:
    def __init__(self, valid):
        self.valid = valid

    def is_valid(self):
        return self.valid


def test_require_action_manager_rejects_invalid_window():
    app.appController._actionManager = DummyActionManager(False)

    ok, message = app._require_action_manager("iniciar a pesca")

    assert ok is False
    assert "janela selecionada" in message.lower()
    assert app.appController._actionManager is None


def test_require_action_manager_accepts_valid_window():
    app.appController._actionManager = DummyActionManager(True)

    ok, message = app._require_action_manager("capturar a runa")

    assert ok is True
    assert message == ""


def test_training_tick_retries_when_target_becomes_available(monkeypatch):
    app.appController._training = app.TrainingStateMachine()
    app.appController._training.start()
    app.battle_list_region = app.BattleListRegion(left=0, top=0, width=200, height=100, monitor=1)

    calls = {"count": 0}

    def fake_should_attack(region):
        calls["count"] += 1
        return calls["count"] >= 2

    monkeypatch.setattr(app, "should_attack_first_target_if_available", fake_should_attack)
    monkeypatch.setattr(app, "execute_first_battle_target_attack", lambda: (True, "ok"))

    assert app.tick_training_attack() is True
    assert calls["count"] == 2


def test_monitor_rechecks_battle_area_even_without_region_change(monkeypatch):
    app.battle_monitor_active = True
    app.appController._training = app.TrainingStateMachine()
    app.battle_list_region = app.BattleListRegion(left=0, top=0, width=200, height=100, monitor=1)
    app.battle_last_region_signature = b"same-signature"

    calls = {"count": 0}

    monkeypatch.setattr(app, "_get_battle_region_signature", lambda region: b"same-signature")
    monkeypatch.setattr(app, "tick_training_attack", lambda: (calls.__setitem__("count", calls["count"] + 1) or True))
    monkeypatch.setattr(app, "_log_battle_change", lambda region: None)

    app.monitor_battle_region()

    assert calls["count"] == 1


def test_monitor_throttles_battle_change_logs(monkeypatch):
    app.battle_monitor_active = True
    app.appController._training = app.TrainingStateMachine()
    app.battle_list_region = app.BattleListRegion(left=0, top=0, width=200, height=100, monitor=1)
    app.battle_last_scan_at = 100.0
    app.battle_scan_interval_seconds = 10.0

    calls = {"count": 0}

    monkeypatch.setattr(app, "_extract_battle_creature_names", lambda region: ("Slime",))
    monkeypatch.setattr(app, "_count_real_battle_targets", lambda region: 1)
    monkeypatch.setattr(app, "has_selected_target_in_region", lambda region: False)
    monkeypatch.setattr(app, "tick_training_attack", lambda: False)
    monkeypatch.setattr(app.time, "monotonic", lambda: 100.5)

    app.monitor_battle_region()

    assert calls == {"count": 0}
