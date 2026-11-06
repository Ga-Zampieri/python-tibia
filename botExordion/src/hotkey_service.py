"""Um único listener global de teclado para o app inteiro."""
from __future__ import annotations

import logging

from pynput import keyboard

logger = logging.getLogger(__name__)

SHIFT_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


def key_name(key) -> str:
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    return (getattr(key, "name", "") or "").lower()


class HotkeyService:
    """Repassa as teclas sem executar nada no callback, que trava o teclado do Windows."""

    def __init__(self, on_key):
        self.on_key = on_key
        self._shift = False
        self._listener = None

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        if key in SHIFT_KEYS:
            self._shift = True
            return
        try:
            self.on_key(key_name(key), self._shift)
        except Exception:
            logger.exception("Erro ao tratar a tecla")

    def _on_release(self, key) -> None:
        if key in SHIFT_KEYS:
            self._shift = False
