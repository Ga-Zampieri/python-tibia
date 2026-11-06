"""Repetidor: chama uma ação em intervalo fixo, sem apertar tecla no Windows."""
from __future__ import annotations

import logging
import math
import threading

logger = logging.getLogger(__name__)


class AutoHotkey:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.key = ""

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def start(self, key: str, interval_seconds, action) -> bool:
        try:
            interval = float(str(interval_seconds).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise ValueError("O intervalo precisa ser um número em segundos.") from exc
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("O intervalo precisa ser maior que zero.")
        if self.is_running:
            return False

        self.key = key
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(key, interval, action), daemon=True, name="repetidor"
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self, key, interval, action) -> None:
        try:
            while not self._stop_event.is_set():
                action(key)
                if self._stop_event.wait(interval):
                    break
        except Exception:
            logger.exception("Erro no repetidor")
            self._stop_event.set()
