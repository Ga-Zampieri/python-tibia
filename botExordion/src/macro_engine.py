from __future__ import annotations

from typing import Any, List


class MacroStep:
    def __init__(self, name: str, *args: Any) -> None:
        self.name = name
        self.args = args

    def __repr__(self) -> str:
        return f"MacroStep(name={self.name!r}, args={self.args!r})"


class MacroEngine:
    def __init__(self, backend=None) -> None:
        self.backend = backend
        self.steps: List[MacroStep] = []

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def add_step(self, step: MacroStep) -> None:
        self.steps.append(step)

    def run_simulation(self) -> List[MacroStep]:
        executed: List[MacroStep] = []
        for step in self.steps:
            executed.append(step)
            if self.backend is not None:
                method = getattr(self.backend, step.name, None)
                if method is not None:
                    method(*step.args)
        return executed

    def clear(self) -> None:
        self.steps.clear()
