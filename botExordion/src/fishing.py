import random
import logging
from pynput import mouse, keyboard
import threading
import time
from .status import Status


class Pesca:
    def __init__(self, action_manager):
        self._action_manager = action_manager
        self._thread = None
        self._stop_event = threading.Event()
        self._kb_listener = None
        self.varinha = None
        self.watersCoords = []
        self.status = Status.Inactive
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _on_key_press(self, key):
        try:
            if key == keyboard.Key.esc:
                self.logger.info("ESC pressionado — parando bot")
                self._stop_event.set()
                self.status = Status.Inactive
                return False
        except Exception as e:
            self.logger.error(f"Erro no handler de tecla: {e}")

    def Pescar(self):
        if self.status == Status.Active:
            return self.stop()
        return self.start()

    def start(self):
        try:
            if self._thread and self._thread.is_alive():
                self.logger.info("Bot já está rodando ou finalizando")
                return False

            if not self.varinha:
                self.logger.error("Varinha não configurada")
                return False
            if not self.watersCoords:
                self.logger.error("Nenhuma água configurada")
                return False
            if not self._action_manager or not self._action_manager.is_valid():
                self.logger.error("Action manager inválido")
                return False

            self._stop_event.clear()
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kb_listener.daemon = True
            self._kb_listener.start()

            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self.status = Status.Active
            self.logger.info("Bot de pesca iniciado")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao iniciar bot: {e}")
            return False

    def stop(self):
        try:
            self._stop_event.set()
            self.status = Status.Inactive
            if self._kb_listener:
                try:
                    self._kb_listener.stop()
                except Exception as e:
                    self.logger.error(f"Erro ao parar listener de teclado: {e}")
                self._kb_listener = None
            if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
                self._thread.join(timeout=2)
            if self._thread and not self._thread.is_alive():
                self._thread = None
            self.logger.info("Bot parado")
            return False
        except Exception as e:
            self.logger.error(f"Erro ao parar bot: {e}")
            return False

    def getFishingRod(self):
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False

        try:
            print("Clique na varinha no inventário...")
            coords = {}

            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(10)
            listener.stop()

            if 'x' in coords:
                self.varinha = (coords['x'], coords['y'])
                print(f"Varinha configurada em: {self.varinha}")
                return True
            return False
        except Exception as e:
            print(f"Erro ao localizar varinha: {e}")
            return False

    def getWaters(self, count: int = 5, timeout: int = 20):
        collected = []
        listener = None

        def _on_click(x, y, button, pressed):
            if pressed:
                collected.append((int(x), int(y)))
                print(f"Água {len(collected)}/{count}: {collected[-1]}")
                if len(collected) >= count:
                    return False

        try:
            self.watersCoords = []
            print(f"Clique em {count} locais de água...")
            listener = mouse.Listener(on_click=_on_click)
            listener.start()

            end_time = time.time() + timeout
            while time.time() < end_time and len(collected) < count:
                time.sleep(0.1)

            self.watersCoords = collected
            print(f"Total de águas: {len(self.watersCoords)}")
            return True
        except Exception as e:
            print(f"Erro ao localizar águas: {e}")
            return False
        finally:
            if listener is not None:
                listener.stop()

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Dorme em pequenos intervalos para reagir rápido ao ESC.
        Retorna False se o stop_event foi acionado durante a espera."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        return True

    def _run(self):
        try:
            self.logger.info("Iniciando ciclo de pesca...")
            while not self._stop_event.is_set():

                for water in self.watersCoords:
                    for _ in range(3):
                        if self._stop_event.is_set():
                            break

                        randX = random.randint(-10, 10)
                        randY = random.randint(-10, 10)
                        varinha_pos = (self.varinha[0] + randX, self.varinha[1] + randY)
                        water_pos = (water[0] + randX, water[1] + randY)

                        self._action_manager.move_mouse(varinha_pos)
                        if not self._action_manager.right_click(varinha_pos):
                            continue

                        if not self._sleep_interruptible(0.5):
                            break

                        if self._stop_event.is_set():
                            break
                        self._action_manager.move_mouse(water_pos)
                        if not self._action_manager.left_click(water_pos):
                            continue

                        if not self._sleep_interruptible(0.5):
                            break

        except Exception as e:
            self.logger.error(f"Erro fatal: {e}")
        finally:
            self.status = Status.Inactive
            self.logger.info("Bot parado")

    def resetCoordinates(self):
        self.varinha = None
        self.watersCoords = []
        print("Coordenadas resetadas.")