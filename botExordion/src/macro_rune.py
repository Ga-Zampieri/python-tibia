from pynput import mouse, keyboard
import threading
import os
import json
from time import sleep
from status import Status


class Runa:
    def __init__(self, action_manager):
        self._action_manager = action_manager
        self._thread = None
        self._stop_event = threading.Event()
        self._kb_listener = None
        self._mappings = {}
        self._mappings_file = os.path.join(os.path.dirname(__file__), "../assets/runa_mappings.json")
        self._on_status_change = None
        self.status = Status.Inactive

    def set_status_callback(self, callback_function):
        self._on_status_change = callback_function
        print("Callback de status conectado à Pesca")

    def _update_status(self, new_status):
        old_status = self.status
        self.status = new_status
        if old_status != new_status and self._on_status_change:
            print(f"Pesca: Status mudou de {old_status} para {new_status}")
            self._on_status_change(new_status)

    def Atacar(self):
        if self.status == Status.Inactive:
            self._start()
        else:
            self._stop()
            
    def equipRuna(self, key_name: str = None) -> bool:
        if not key_name:
            print("É necessário especificar a hotkey.")
            return False

        coords = self._mappings.get(key_name)
        if not coords:
            print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
            return False
        targetX, targetY = coords

        self._action_manager.right_click((targetX, targetY))
        sleep(0.05)
        return True

    def _start(self):
        if self._thread and self._thread.is_alive():
            return

        if self._kb_listener is None or not getattr(self._kb_listener, "is_alive", lambda: False)():
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kb_listener.daemon = True
            self._kb_listener.start()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._update_status(Status.Active)

    def _stop(self):
        self._stop_event.set()
        if self._kb_listener:
            self._kb_listener.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join()
        self._thread = None
        self._update_status(Status.Inactive)
                
    def _run(self):
        while not self._stop_event.is_set():
            sleep(0.05)

    def _on_key_press(self, key):
        name = self._key_to_name(key)
        if name == "esc":
            self._stop()
            return
        if name in self._mappings:
            self.equipRuna(name)

    def _key_to_name(self, key):
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        if hasattr(key, "name"):
            return key.name.lower()
        return str(key).lower()

    def getRuna(self, key_name: str = None, timeout: int = 10):
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False
        coords = {}
        listener = mouse.Listener(on_click=_on_click)
        listener.start()
        listener.join(timeout)
        listener.stop()
        if 'x' in coords:
            if key_name:
                self.map_key_to_coords(key_name, coords['x'], coords['y'])
                return True
            else:
                print("Necessário informar uma hotkey para bindar a runa capturada.")
                return False
        else:
            print("Nenhuma coordenada registrada (timeout).")
            return False
    


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
        else:
            self._mappings = {} 
            print("Todos os mapeamentos foram resetados.")


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