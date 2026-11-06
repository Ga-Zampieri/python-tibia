"""Captura guiada de cliques na janela do jogo, sem travar a interface."""
from __future__ import annotations

import threading

from pynput import mouse


class ClickCapture:
    def __init__(self, am, count: int, timeout: float, on_point, on_done):
        self.am = am
        self.count = count
        self.timeout = timeout
        self.on_point = on_point
        self.on_done = on_done
        self.points = []
        self._finished = threading.Event()
        self._listener = None

    def start(self) -> None:
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.start()
        threading.Thread(target=self._wait, daemon=True, name="captura").start()

    def cancel(self) -> None:
        self._finished.set()

    def _on_click(self, x, y, button, pressed):
        # Clique fora do jogo (no próprio bot, por exemplo) não conta.
        if not pressed or not self.am.contains_screen_point((x, y)):
            return None
        self.points.append(list(self.am.screen_to_client((x, y))))
        self.on_point(len(self.points))
        if len(self.points) >= self.count:
            self._finished.set()
            return False
        return None

    def _wait(self) -> None:
        self._finished.wait(self.timeout)
        self._listener.stop()
        self.on_done(self.points)
