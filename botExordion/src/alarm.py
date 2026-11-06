"""Decide quando a battle list merece um alarme."""
from __future__ import annotations


class AlarmMonitor:
    def __init__(self, cooldown: float = 10.0):
        self.cooldown = cooldown
        self.baseline = None
        self._next_alert = 0.0

    def reset(self) -> None:
        self.baseline = None
        self._next_alert = 0.0

    def evaluate(self, snapshot, now: float, has_allowed_names: bool):
        """Mensagem do alarme, ou None.

        Com nomes permitidos, qualquer nome de fora dispara. Sem eles, dispara
        quando há mais gente na lista do que havia ao ligar o alarme.
        """
        count = len(snapshot.rows)
        if self.baseline is None:
            self.baseline = count

        if has_allowed_names:
            unknown = sum(1 for row in snapshot.rows if not row.allowed)
            message = f"{unknown} nome(s) desconhecido(s) na battle list!" if unknown else None
        elif count > self.baseline:
            message = f"Battle list subiu de {self.baseline} para {count}!"
        else:
            message = None

        if message is None or now < self._next_alert:
            return None
        self._next_alert = now + self.cooldown
        return message
