import logging
import math
import threading

from pynput import keyboard


class AutoHotkey:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self._key = None
        self._interval = 0.0
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def parse_key(key_name: str):
        normalized = str(key_name or "").strip().lower()
        if len(normalized) == 1:
            return keyboard.KeyCode.from_char(normalized)

        key = getattr(keyboard.Key, normalized, None)
        if key is None:
            raise ValueError(f"Hotkey inválida: {key_name!r}")
        return key

    @property
    def is_running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    def start(self, key_name: str, interval_seconds: float) -> bool:
        key = self.parse_key(key_name)
        try:
            interval = float(interval_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("O intervalo precisa ser um número em segundos.") from exc
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("O intervalo precisa ser maior que zero.")
        if self.is_running:
            return False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
            if self._thread.is_alive():
                return False

        self._key = key
        self._interval = interval
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        try:
            controller = keyboard.Controller()
            while not self._stop_event.is_set():
                pressed = False
                try:
                    controller.press(self._key)
                    pressed = True
                finally:
                    if pressed:
                        controller.release(self._key)
                if self._stop_event.wait(self._interval):
                    break
        except Exception:
            self.logger.exception("Erro ao pressionar a hotkey automática.")
            self._stop_event.set()
