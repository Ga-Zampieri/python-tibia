import app


def test_demo_mode_runs_without_gui():
    assert app.main(["--demo"]) == 0


def test_main_opens_the_interface(monkeypatch):
    opened = []
    monkeypatch.setattr(app, "setup_logging", lambda: None)
    monkeypatch.setattr(app, "launch_ui", lambda: opened.append(True))

    assert app.main([]) == 0
    assert opened == [True]


def test_interface_failure_returns_error_code(monkeypatch):
    def explode():
        raise RuntimeError("sem display")

    monkeypatch.setattr(app, "setup_logging", lambda: None)
    monkeypatch.setattr(app, "launch_ui", explode)

    assert app.main([]) == 1
