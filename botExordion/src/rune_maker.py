"""Rune maker AFK: blank rune para a mão, conjura, runa pronta para a mochila."""
from __future__ import annotations

import logging
import threading

from . import battle_vision

logger = logging.getLogger(__name__)

SLOT_RADIUS = 12
HAND_CHECKS = 8  # com a espera abaixo, dá 2 s para o servidor mover a blank
HAND_CHECK_SECONDS = 0.25


class RuneMaker:
    def __init__(self, config: dict, get_mana, log=logger.info, get_frame=lambda: None, alert=None):
        self.am = None
        self.config = config
        self.get_mana = get_mana
        self.log = log
        self.get_frame = get_frame
        self.alert = alert or log
        self.casts = 0
        self._blank_sprite = None
        self._warned_no_image = False
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
        self._blank_sprite = None
        self._warned_no_image = False
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

    def _read_hand(self):
        frame = self.get_frame()
        if frame is None:
            return None
        x, y = self.config["hand"]
        size = SLOT_RADIUS * 2
        slot = battle_vision.crop(frame, (x - SLOT_RADIUS, y - SLOT_RADIUS, size, size))
        return slot if slot.size else None

    def _give_up(self, message: str) -> bool:
        self._stop_event.set()
        self.alert(message)
        return False

    def _blank_in_hand(self, empty_hand) -> bool:
        """Sem imagem não dá para concluir nada, e o ciclo segue como antes."""
        for _ in range(HAND_CHECKS):
            hand = self._read_hand() if empty_hand is not None else None
            if hand is None:
                if not self._warned_no_image:
                    self._warned_no_image = True
                    self.log("Rune maker: sem imagem do jogo, não dá para conferir as blank runes.")
                return True
            if not battle_vision.same_image(hand, empty_hand):
                break
            if self._stop_event.wait(HAND_CHECK_SECONDS):
                return False
        else:
            return self._give_up("Rune maker parou: a blank rune não chegou na mão. "
                                 "Acabaram, ou a mão não estava livre?")
        if self._blank_sprite is None:
            self._blank_sprite = hand
        elif not battle_vision.same_image(hand, self._blank_sprite):
            return self._give_up("Rune maker parou: veio outro item para a mão. As blank runes acabaram?")
        return True

    def cycle(self) -> bool:
        config = self.config
        empty_hand = self._read_hand()
        if not self._guarded_drag(config["blank"], config["hand"]):
            return False
        if self._stop_event.wait(0.5):
            return False
        if not self._blank_in_hand(empty_hand):
            return False
        self.am.send_text(config["spell"])
        self._stop_event.wait(max(0.2, float(config["cast_wait"])))
        # Mesmo se pararem agora, a runa não fica presa na mão.
        if not self._guarded_drag(config["hand"], config["output"]):
            return False
        self.casts += 1
        return True
