"""Rune maker AFK: blank rune para a mão, conjura, runa pronta para a mochila."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class RuneMaker:
    def __init__(self, config: dict, get_mana, log=logger.info):
        self.am = None
        self.config = config
        self.get_mana = get_mana
        self.log = log
        self.casts = 0
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def missing(self) -> str:
        labels = {"blank": "blank rune", "hand": "mão", "output": "destino", "spell": "magia"}
        for field, label in labels.items():
            if not self.config[field]:
                return label
        return ""

    def start(self) -> bool:
        if self.is_running or self.am is None or self.missing():
            return False
        self.casts = 0
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="rune-maker")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    def has_mana(self) -> bool:
        mana = self.get_mana()
        return mana is None or mana >= float(self.config["mana_percent"])

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                if not self.has_mana():
                    self._stop_event.wait(1.0)
                    continue
                self.cycle()
                self._stop_event.wait(max(1.0, float(self.config["interval"])))
        except Exception:
            logger.exception("Erro no rune maker")
            self._stop_event.set()

    def _guarded_drag(self, start, end) -> bool:
        with self.am.guarded() as blocked:
            if not blocked:
                self.log("Rune maker: não foi possível bloquear o input (precisa de admin).")
                self._stop_event.set()
                return False
            return self.am.drag(start, end)

    def cycle(self) -> bool:
        config = self.config
        if not self._guarded_drag(config["blank"], config["hand"]):
            return False
        if self._stop_event.wait(0.5):
            return False
        self.am.send_text(config["spell"])
        self._stop_event.wait(max(0.2, float(config["cast_wait"])))
        # Mesmo se pararem agora, a runa não fica presa na mão.
        if not self._guarded_drag(config["hand"], config["output"]):
            return False
        self.casts += 1
        return True
