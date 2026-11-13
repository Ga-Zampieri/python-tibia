"""Painel pequeno por cima do jogo com os módulos ligados e os atalhos."""
from __future__ import annotations

import ctypes
import logging
import tkinter as tk

from .theme import ACCENT, BG, FONT, MUTED, TEXT

logger = logging.getLogger(__name__)

OVERLAY_MARGIN = 8
OFFSCREEN = -32000
GWL_EXSTYLE = -20
# Camada que o mouse atravessa, fora da barra de tarefas e que nunca recebe o foco.
OVERLAY_STYLE = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000


class GameOverlay:
    """Painel pequeno por cima do jogo: módulos ligados e atalhos.

    Nunca é escondido de verdade: mostrar uma janela pelo Tk a ativa, o jogo
    perderia o foco e o painel sumiria de novo. Fora de uso, fica fora da tela."""

    def __init__(self, master):
        self.window = tk.Toplevel(master, bg=BG)
        self.window.overrideredirect(True)
        self.window.geometry(f"+{OFFSCREEN}+{OFFSCREEN}")
        self.window.attributes("-topmost", True)
        self.frame = tk.Frame(self.window, bg=BG, padx=8, pady=5)
        self.frame.pack()
        self.rows = None
        self.position = None
        self.window.attributes("-alpha", 0.88)
        self.window.update_idletasks()
        self._make_click_through()  # depois do alpha: o Tk refaz o estilo ao mudá-lo

    def _make_click_through(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.window.wm_frame(), 16)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | OVERLAY_STYLE)
        except Exception:
            logger.exception("Não deu para deixar o painel transparente ao mouse")

    def show(self, state):
        if state is None:
            self._move(OFFSCREEN, OFFSCREEN)
            return
        if state["rows"] != self.rows:
            self.rows = state["rows"]
            for child in self.frame.winfo_children():
                child.destroy()
            for line, (title, hotkey, on) in enumerate(self.rows):
                tk.Label(self.frame, text="●", fg=ACCENT if on else MUTED, bg=BG, font=(FONT, 9)).grid(
                    row=line, column=0, sticky="w")
                tk.Label(self.frame, text=title, fg=TEXT if on else MUTED, bg=BG, font=(FONT, 10)).grid(
                    row=line, column=1, sticky="w", padx=(4, 12))
                tk.Label(self.frame, text=hotkey, fg=MUTED, bg=BG, font=(FONT, 9)).grid(
                    row=line, column=2, sticky="e")
            self.window.update_idletasks()
        left, top, width, _ = state["client"]
        x = left + OVERLAY_MARGIN
        if state["corner"] == "right":
            x = left + width - self.window.winfo_reqwidth() - OVERLAY_MARGIN
        self._move(x, top + OVERLAY_MARGIN)

    def _move(self, x, y):
        if self.position != (x, y):
            self.position = (x, y)
            self.window.geometry(f"+{x}+{y}")

    def destroy(self):
        self.window.destroy()
