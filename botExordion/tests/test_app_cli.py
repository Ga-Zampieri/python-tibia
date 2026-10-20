import app


def test_main_demo_mode_runs_without_gui():
    assert app.main(["--demo"]) == 0


def test_main_without_gui_falls_back_to_demo_in_headless_environment(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert app.main([]) == 0
