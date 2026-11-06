"""Rotinas de manutenção: comer, anti-idle e regras de HP/mana."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class Survival:
    def __init__(self, config: dict, run_action):
        self.am = None
        self.config = config
        self.run_action = run_action
        self.reset()

    def reset(self) -> None:
        self._next_eat = 0.0
        self._next_idle = None
        self._rule_ready = {}
        self._turn_up = True

    def tick(self, now: float, hp, mana) -> None:
        if self.am is None:
            return
        self._eat(now)
        self._anti_idle(now)
        for index, rule in enumerate(self.config["rules"]):
            self._apply_rule(index, rule, now, hp, mana)

    def _eat(self, now: float) -> None:
        eat = self.config["eat"]
        if eat["enabled"] and eat["pos"] and now >= self._next_eat:
            self._next_eat = now + max(1.0, float(eat["interval"]))
            self.am.right_click(eat["pos"])

    def _anti_idle(self, now: float) -> None:
        idle = self.config["anti_idle"]
        if not idle["enabled"]:
            self._next_idle = None
            return
        interval = max(10.0, float(idle["interval"]))
        if self._next_idle is None:
            self._next_idle = now + interval
        elif now >= self._next_idle:
            self._next_idle = now + interval
            self.am.turn("up" if self._turn_up else "down")
            self._turn_up = not self._turn_up

    def _apply_rule(self, index: int, rule: dict, now: float, hp, mana) -> None:
        if not rule["enabled"] or not rule["action"]:
            return
        value = hp if rule["stat"] == "hp" else mana
        if value is None:
            return
        limit = float(rule["percent"])
        triggered = value < limit if rule["op"] == "<" else value > limit
        if triggered and now >= self._rule_ready.get(index, 0.0):
            self._rule_ready[index] = now + max(0.2, float(rule["cooldown"]))
            self.run_action(rule["action"])
