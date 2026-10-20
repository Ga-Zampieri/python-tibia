from pynput import mouse, keyboard
import threading
import os
import json
from time import sleep, monotonic
from .status import Status


class Runa:
    def __init__(self, action_manager):
        self._thread = None
        self._action_manager = action_manager
        self._stop_event = threading.Event()
        self._kb_listener = None
        self._mappings = {}
        self._mappings_file = os.path.join(os.path.dirname(__file__), "../assets/runa_mappings.json")
        self._action_lock = threading.Lock()
        self.status = Status.Inactive

    @staticmethod
    def _set_cursor_pos(x: int, y: int) -> bool:
        try:
            import ctypes
            ctypes.windll.user32.SetCursorPos(x, y)
            return True
        except Exception:
            return False

    @staticmethod
    def _get_cursor_pos():
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        except Exception:
            return None, None

    @staticmethod
    def _send_right_click():
        try:
            import ctypes
            MOUSEEVENTF_RIGHTDOWN = 0x0008
            MOUSEEVENTF_RIGHTUP = 0x0010
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            sleep(0.02)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        except Exception as e:
            print(f"Erro ao enviar clique direito: {e}")

    def equipRuna(self, key_name: str = None) -> bool:
        if not key_name:
            print("É necessário especificar a hotkey.")
            return False

        coords = self._mappings.get(key_name)
        if not coords:
            print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
            return False
        targetX, targetY = coords

        if not self._action_lock.acquire(blocking=False):
            print("Ação já em progresso. Ignorando novo pedido.")
            return False

        try:
            startX, startY = self._get_cursor_pos()
            if not self._set_cursor_pos(targetX, targetY):
                print("Falha ao mover o cursor para a posição da runa.")
                return False

            self._send_right_click()
            sleep(0.05)

            if startX is not None and startY is not None:
                self._set_cursor_pos(startX, startY)

            return True
        except Exception as e:
            print(f"Erro durante equipagem da runa: {e}")
            return False
        finally:
            self._action_lock.release()

    def Atacar(self, status: bool):
        if status:
            if self._thread and self._thread.is_alive():
                self.status = Status.Active
                return

            if self._kb_listener is None or not getattr(self._kb_listener, "is_alive", lambda: False)():
                self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
                self._kb_listener.daemon = True
                self._kb_listener.start()

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self.status = Status.Active
        else:
            self._stop_event.set()
            if self._kb_listener:
                self._kb_listener.stop()
            self._kb_listener = None

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1)
            self._thread = None
            self.status = Status.Inactive

    def _run(self):
        try:
            while not self._stop_event.is_set():
                sleep(0.1)
        except Exception as e:
            print(f"Erro no loop de ataque: {e}")

    def _on_key_press(self, key):
        try:
            name = self._key_to_name(key)
            if name == "esc":
                self._stop_event.set()
                return
            if name in self._mappings:
                self.equipRuna(name)
        except Exception as e:
            print(f"Erro no _on_key_press: {e}")

    @staticmethod
    def _key_to_name(key):
        try:
            if hasattr(key, "char") and key.char:
                return key.char.lower()
            if hasattr(key, "name"):
                return key.name.lower()
        except Exception:
            pass
        return str(key).lower()

    def getRuna(self, key_name: str = None, timeout: int = 10):
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False
        try:
            coords = {}
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)
            listener.stop()
            if 'x' in coords:
                if key_name:
                    self.map_key_to_coords(key_name, coords['x'], coords['y'])
                    self.map_key_to_coords(key_name, coords['x'], coords['y'])
                    return True
                else:
                    print("Necessário informar uma hotkey para bindar a runa capturada.")
                    return False
            else:
                print("Nenhuma coordenada registrada (timeout).")
                return False
        except Exception as e:
            print(f"Erro ao localizar runa: {e}")

    def map_key_to_coords(self, key_name: str, x: int, y: int):
        self._mappings[key_name] = (int(x), int(y))
        print(f"Mapeado: '{key_name}' -> ({x}, {y})")

    def remove_mapping(self, key_name: str):
        if key_name in self._mappings:
            del self._mappings[key_name]
            print(f"Removido mapeamento para '{key_name}'")
        else:
            print(f"Nenhum mapeamento encontrado para '{key_name}'")

    def list_mappings(self):
        if not self._mappings:
            print("Nenhum mapeamento de runa definido.")
            return
        print("Mapeamentos atuais:")
        for k, v in self._mappings.items():
            print(f"  '{k}' -> X {v[0]}, Y {v[1]}")

    def resetRuna(self, key_name: str = None):
        if key_name:
            self.remove_mapping(key_name)
            self.remove_mapping(key_name)
        else:
            self._mappings = {}
            self._mappings = {}

    def save_mappings(self):
        try:
            with open(self._mappings_file, "w", encoding="utf-8") as f:
                json.dump(self._mappings, f, ensure_ascii=False, indent=2)
            print(f"Mapeamentos salvos em {self._mappings_file}")
            return True
        except Exception as e:
            print(f"Erro ao salvar mapeamentos: {e}")

    def load_mappings(self):
        try:
            if os.path.exists(self._mappings_file):
                with open(self._mappings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._mappings = {k: (int(v[0]), int(v[1])) for k, v in data.items()}
                print(f"Mapeamentos carregados de {self._mappings_file}")
            return True
        except Exception as e:
            print(f"Erro ao carregar mapeamentos: {e}")