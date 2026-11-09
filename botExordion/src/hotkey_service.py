"""Um único listener global de teclado para o app inteiro."""
from __future__ import annotations

import logging

from pynput import keyboard

logger = logging.getLogger(__name__)

Key = keyboard.Key
MODIFIERS = {
    Key.shift: "shift", Key.shift_l: "shift", Key.shift_r: "shift",
    Key.ctrl: "ctrl", Key.ctrl_l: "ctrl", Key.ctrl_r: "ctrl",
    Key.alt: "alt", Key.alt_l: "alt", Key.alt_r: "alt", Key.alt_gr: "alt",
}
MODIFIER_ORDER = ("ctrl", "alt", "shift")


def key_name(key) -> str:
    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()
    name = getattr(key, "name", None)
    if name:
        return name.lower()
    # Com Ctrl, o Windows entrega um caractere de controle ou nenhum no lugar da letra.
    vk = getattr(key, "vk", None)
    if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()
    return ""


def combo_name(name: str, mods=()) -> str:
    """Forma canônica de um atalho, como `ctrl+shift+f1`."""
    return "+".join([mod for mod in MODIFIER_ORDER if mod in mods] + [name])


def _key_id(key):
    # O char muda se o Shift for solto antes da tecla; o vk não.
    return getattr(key, "vk", None) or key


class HotkeyService:
    """Repassa as teclas sem executar nada no callback, que trava o teclado do Windows."""

    def __init__(self, on_key):
        self.on_key = on_key
        self._held = {}
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
        key_id = _key_id(key)
        repeat = key_id in self._held
        self._held[key_id] = key
        name = key_name(key)
        if key in MODIFIERS or not name:
            return
        mods = {MODIFIERS[held] for held in self._held.values() if held in MODIFIERS}
        try:
            self.on_key(name, mods, repeat)
        except Exception:
            logger.exception("Erro ao tratar a tecla")

    def _on_release(self, key) -> None:
        self._held.pop(_key_id(key), None)
