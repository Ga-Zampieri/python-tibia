from src.backend import SimulatedInputBackend


def test_simulated_backend_click_and_batch():
    backend = SimulatedInputBackend()
    backend.move_to(10, 20)
    backend.click_left()
    backend.press_key('a')
    backend.execute_batch([
        ('move_to', (30, 40)),
        ('click_left', ()),
    ])
    assert backend.position == (30, 40)
    assert backend.last_key == 'a'
    backend.cancel_pending_actions()
    assert backend.cancelled is True
