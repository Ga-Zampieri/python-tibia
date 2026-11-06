import logging
import random
import threading
import time

from .status import Status

logger = logging.getLogger(__name__)


class Pesca:
    def __init__(self, config: dict):
        self.am = None
        self.config = config
        self._thread = None
        self._stop_event = threading.Event()
        self.status = Status.Inactive
        self.attempts = 0

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        if self.am is None or not self.am.is_valid():
            return False
        if not self.config["rod"] or not self.config["waters"]:
            return False
        self._stop_event.clear()
        self.attempts = 0
        self.status = Status.Active
        self._thread = threading.Thread(target=self._run, daemon=True, name="pesca")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        self.status = Status.Inactive
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _sleep_interruptible(self, seconds: float) -> bool:
        return not self._stop_event.wait(seconds)

    def _cast(self, water) -> None:
        offset_x = random.randint(-10, 10)
        offset_y = random.randint(-10, 10)
        rod = self.config["rod"]
        rod_pos = (rod[0] + offset_x, rod[1] + offset_y)
        water_pos = (water[0] + offset_x, water[1] + offset_y)

        # O lock cobre a mira: outro módulo não pode clicar entre a vara e a água.
        with self.am.lock:
            if not self.am.right_click(rod_pos):
                return
            if not self._sleep_interruptible(0.5):
                return
            if self.am.left_click(water_pos):
                self.attempts += 1
        self._sleep_interruptible(0.5)

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                for water in self.config["waters"]:
                    for _ in range(3):
                        if self._stop_event.is_set():
                            return
                        self._cast(water)
        except Exception:
            logger.exception("Erro fatal na pesca")
        finally:
            self.status = Status.Inactive
