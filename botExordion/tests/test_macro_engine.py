from src.macro_engine import MacroEngine, MacroStep


def test_macro_execution_runs_steps():
    engine = MacroEngine()
    step1 = MacroStep('move_to', 10, 20)
    step2 = MacroStep('click_left')
    engine.add_step(step1)
    engine.add_step(step2)
    results = engine.run_simulation()
    assert results[0].name == 'move_to'
    assert results[1].name == 'click_left'
    assert engine.step_count == 2
