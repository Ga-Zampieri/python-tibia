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
        except Exception as e:
            self.logger.error(f"Erro no handler de tecla: {e}")

    def Pescar(self):
        try:
            if self.status == Status.Inactive:
                if self._thread and self._thread.is_alive():
                    self.logger.info("Bot já está rodando")
                    return

                if not self.varinha:
                    self.logger.error("Varinha não configurada")
                    return
                if not self.watersCoords:
                    self.logger.error("Nenhuma água configurada")
                    return
                if not self._action_manager or not self._action_manager.is_valid():
                    self.logger.error("Action manager inválido")
                    return

                self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
                self._kb_listener.daemon = True
                self._kb_listener.start()

                self._stop_event.clear()
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
                self.logger.info("Bot de pesca iniciado")
                self.status = Status.Active
                return True

            self.logger.info("Parando bot")
            self._stop_event.set()
            if self._kb_listener:
                self._kb_listener.stop()
                self._kb_listener = None
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1)
            self._thread = None
            self.status = Status.Inactive
            return False
        except Exception as e:
            self.logger.error(f"Erro ao iniciar/parar bot: {e}")
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

        def _on_click(x, y, button, pressed):
            if pressed:
                collected.append((int(x), int(y)))
                print(f"Água {len(collected)}/{count}: {collected[-1]}")
                if len(collected) >= count:
                    return False

        try:
            print(f"Clique em {count} locais de água...")
            listener = mouse.Listener(on_click=_on_click)
            listener.start()

            end_time = time.time() + timeout
            while time.time() < end_time and len(collected) < count:
                time.sleep(0.1)

            listener.stop()
            
            if collected:
                self.watersCoords.extend(collected)
                print(f"Total de águas: {len(self.watersCoords)}")
            return True
        except Exception as e:
            print(f"Erro ao localizar águas: {e}")
            return False

    def _run(self):
        try:
            self.logger.info("Iniciando ciclo de pesca...")
            while not self._stop_event.is_set():
                
                for i, water in enumerate(self.watersCoords):
                    if self._stop_event.is_set():
                        break
                    
                    randX = random.randint(-10, 10)
                    randY = random.randint(-10, 10)
                    varinha_pos = (self.varinha[0] + randX, self.varinha[1] + randY)
                    water_pos = (water[0] + randX, water[1] + randY)

                    self._action_manager.move_mouse(varinha_pos)  # mover mouse para fora da tela
                    if not self._action_manager.right_click(varinha_pos):
                        continue
                    time.sleep(0.5)
                    self._action_manager.move_mouse(water_pos)  # mover mouse para fora da tela
                    if not self._action_manager.left_click(water_pos):
                        continue
                    time.sleep(0.5)

        except Exception as e:
            self.logger.error(f"Erro fatal: {e}")
        finally:
            self.logger.info("Bot parado")

    def resetCoordinates(self):
        self.varinha = None
        self.watersCoords = []
        print("Coordenadas resetadas.")