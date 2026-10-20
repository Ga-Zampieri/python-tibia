from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, List, Tuple


@dataclass
class InputAction:
    name: str
    args: Tuple[Any, ...] = ()


class SimulatedInputBackend:
    """Backend de entrada simulado, usado para testes e automação em ambiente sem cliente real."""

    def __init__(self) -> None:
        self.position = (0, 0)
        self.last_key: str | None = None
        self.cancelled = False
        self.pending: Deque[InputAction] = deque()
        self.button_state = {"left": False, "right": False}
        self.key_state: dict[str, bool] = {}
        self.events: List[str] = []

    def move_to(self, x: int, y: int) -> bool:
        self.position = (int(x), int(y))
        self.events.append(f"move_to:{x},{y}")
        return True

    def move_relative(self, dx: int, dy: int) -> bool:
        x, y = self.position
        self.position = (x + int(dx), y + int(dy))
        self.events.append(f"move_relative:{dx},{dy}")
        return True

    def click_left(self) -> bool:
        self.events.append("click_left")
        return True

    def click_right(self) -> bool:
        self.events.append("click_right")
        return True

    def mouse_down(self, button: str) -> bool:
        self.button_state[button.lower()] = True
        self.events.append(f"mouse_down:{button}")
        return True

    def mouse_up(self, button: str) -> bool:
        self.button_state[button.lower()] = False
        self.events.append(f"mouse_up:{button}")
        return True

    def press_key(self, key: str) -> bool:
        self.last_key = str(key)
        self.key_state[str(key)] = True
        self.events.append(f"press_key:{key}")
        return True

    def release_key(self, key: str) -> bool:
        self.key_state[str(key)] = False
        self.events.append(f"release_key:{key}")
        return True

    def execute_batch(self, actions: List[Tuple[str, tuple]]) -> bool:
        for action, args in actions:
            self.pending.append(InputAction(action, tuple(args)))
        for action in list(self.pending):
            self._apply_action(action)
        self.pending.clear()
        return True

    def _apply_action(self, action: InputAction) -> None:
        name = action.name
        if name == "move_to":
            x, y = action.args
            self.move_to(x, y)
        elif name == "move_relative":
            dx, dy = action.args
            self.move_relative(dx, dy)
        elif name == "click_left":
            self.click_left()
        elif name == "click_right":
            self.click_right()
        elif name == "press_key":
            key = action.args[0]
            self.press_key(key)
        elif name == "release_key":
            key = action.args[0]
            self.release_key(key)

    def cancel_pending_actions(self) -> None:
        self.cancelled = True
        self.pending.clear()

    def reset(self) -> None:
        self.position = (0, 0)
        self.last_key = None
        self.cancelled = False
        self.pending.clear()
        self.button_state = {"left": False, "right": False}
        self.key_state.clear()
        self.events.clear()

    def __repr__(self) -> str:
        return f"SimulatedInputBackend(position={self.position}, last_key={self.last_key})"
