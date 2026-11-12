"""Macros de runa e de puxar item."""
from __future__ import annotations

import logging
from time import sleep

logger = logging.getLogger(__name__)


class MacroRunner:
    def __init__(self, profile: dict, log=logger.info):
        self.am = None
        self.profile = profile
        self.log = log

    def execute(self, key: str) -> bool:
        macro = self.profile["macros"].get(key)
        if macro is None or self.am is None:
            return False
        if macro["mode"] == "drag":
            return self._drag(key, macro)
        return self._use_rune(key, macro)

    def _use_rune(self, key: str, macro: dict) -> bool:
        player = None
        if macro["mode"] == "self":
            player = self.profile["player_position"]
            if not player:
                self.log(f"'{key}': capture a posição do player primeiro.")
                return False
        return self.use_rune_on(macro["pos"], player, f"'{key}'")

    def use_rune_on(self, pos, target, label: str) -> bool:
        """Clica com o direito na runa e, se houver alvo, com o esquerdo nele."""
        if self.am is None:
            return False
        with self.am.guarded() as blocked:
            if not blocked:
                self.log("Não foi possível bloquear o input. Abra o bot como administrador.")
                return False
            try:
                # Com o jogo atrás, o cursor real clicaria na janela que está na frente.
                if self.am.is_foreground():
                    return self._rune_with_cursor(pos, target)
                return self._rune_with_messages(pos, target)
            except Exception as exc:
                self.log(f"Erro ao usar a runa de {label}: {exc}")
                return False

    def _rune_with_cursor(self, pos, player) -> bool:
        original = self.am.get_cursor()
        try:
            self.am.click_with_cursor(pos, "right")
            sleep(0.05)
            if player:
                self.am.click_with_cursor(player, "left")
            return True
        finally:
            self.am.set_cursor(original)

    def _rune_with_messages(self, pos, player) -> bool:
        if not self.am.right_click(pos):
            return False
        sleep(0.05)
        return self.am.left_click(player) if player else True

    def _drag(self, key: str, macro: dict) -> bool:
        if not macro.get("end"):
            self.log(f"'{key}': ponto final do arrasto não configurado.")
            return False
        with self.am.guarded() as blocked:
            if not blocked:
                self.log("Não foi possível bloquear o input. Abra o bot como administrador.")
                return False
            if self.profile["drag_in_background"]:
                return self.am.drag(macro["pos"], macro["end"])
            return self.am.drag_with_cursor(macro["pos"], macro["end"])
