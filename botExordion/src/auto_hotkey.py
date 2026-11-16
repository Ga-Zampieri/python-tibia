"""Repetidor: várias teclas, cada uma no seu intervalo, sem apertar tecla no Windows.

Um só fio dispara todas, uma de cada vez: duas teclas do repetidor nunca se
atropelam. A lista é relida a cada volta, então mudar uma tecla ou um intervalo
na tela vale sem desligar.
"""
from __future__ import annotations

import logging
import math
import threading
import time

logger = logging.getLogger(__name__)

RELOAD_SECONDS = 0.5  # de quanto em quanto tempo, no máximo, relê a lista


def parse_interval(value) -> float:
    try:
        interval = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError("O intervalo precisa ser um número em segundos.") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("O intervalo precisa ser maior que zero.")
    return interval


class AutoHotkey:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def start(self, get_entries, action) -> bool:
        """get_entries() devolve [(tecla, intervalo em s)]; action(tecla) age."""
        if self.is_running:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(get_entries, action), daemon=True,
                                        name="repetidor")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self, get_entries, action) -> None:
        due = {}  # tecla -> quando dispara de novo
        try:
            while not self._stop_event.is_set():
                entries = dict(get_entries())
                now = time.monotonic()
                for key in list(due):
                    if key not in entries:
                        del due[key]
                for key in entries:
                    due.setdefault(key, now)  # tecla nova dispara já
                if not due:
                    self._stop_event.wait(RELOAD_SECONDS)
                    continue
                key = min(due, key=due.get)
                wait = due[key] - now
                if wait > 0:
                    if self._stop_event.wait(min(wait, RELOAD_SECONDS)):
                        break
                    continue
                action(key)
                due[key] = time.monotonic() + entries[key]
        except Exception:
            logger.exception("Erro no repetidor")
            self._stop_event.set()
