from pynput import mouse, keyboard
import threading
import os
import json
from .status import Status


class Runa:
    def __init__(self, action_manager):
        self._action_manager = action_manager
        self._thread = None
        self._stop_event = threading.Event()
        self._kb_listener = None
        self._mappings = {}
        self._mappings_file = os.path.join(os.path.dirname(__file__), "../assets/runa_mappings.json")
        self._action_lock = threading.Lock()
        self.status = Status.Inactive
        

    def _key_to_name(self, key):
        """Normaliza um objeto Key/KeyCode para string (ex: 'f1', 'a', 'esc')."""
        try:
            # KeyCode (letras/teclas imprimíveis)
            if hasattr(key, "char") and key.char is not None:
                return key.char.lower()
        except Exception:
            pass
        # Key especial (Key.f1) -> 'f1'
        return str(key).split('.')[-1]

    def _on_key_press(self, key):
        try:
            name = self._key_to_name(key)
            if name == "esc":
                self._stop_event.set()
                return
            # se existir mapeamento para a tecla, equipar a runa correspondente
            if name in self._mappings:
                try:
                    self.equipRuna(name)
                except Exception as e:
                    print(f"Erro ao tentar equipar runa ({name}): {e}")
        except Exception:
            pass
    
    def equipRuna(self, key_name: str = None) -> bool:
        """Mover -> clicar direito -> voltar.
        Implementação simples e determinística seguindo a lógica do _run:
        move para a posição da runa via action_manager.move_mouse,
        faz right_click, aguarda e volta para a posição inicial.
        """
        if not key_name:
            print("É necessário especificar a hotkey.")
            return False

        coords = self._mappings.get(key_name)
        if not coords:
            print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
            return False
        target = (int(coords[0]), int(coords[1]))

        # evita concorrência
        if not self._action_lock.acquire(blocking=False):
            print("Ação já em progresso. Ignorando novo pedido.")
            return False

        try:
            if not self._action_manager.move_mouse(target):
                print("Falha ao mover o mouse para a runa.")
                return False

            if not self._action_manager.right_click(target):
                print("Falha ao executar clique direito na runa.")
                return False
            
            return True
        except Exception as e:
            print(f"Erro durante equipagem da runa: {e}")
            return False
        finally:
            self._action_lock.release()


    def Atacar(self, status: bool):
        if status:
            if self._thread and self._thread.is_alive():
                return  # já rodando
            if self._kb_listener is None or not getattr(self._kb_listener, "is_alive", lambda: False)():
                self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
                self._kb_listener.daemon = True
                self._kb_listener.start()
            self._stop_event.clear()
        else:
            self._stop_event.set()
            try:
                if self._kb_listener is not None:
                    self._kb_listener.stop()
            except Exception:
                pass
            self._kb_listener = None


    def getRuna(self, key_name: str = None, timeout: int = 10):
        """Captura um clique do mouse e registra como runa.

        Se key_name for fornecido, armazena em _mappings[key_name], caso contrário
        define runaX/runaY padrão.
        """
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False  # stop listener
        try:
            print("Clique na posição da runa (ou aguarde timeout)...")
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
        except Exception as e:
            print(f"Erro ao localizar runa: {e}")
        finally:
            pass


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
        return True


    def resetRuna(self, key_name: str = None):
        if key_name:
            self.remove_mapping(key_name)
        else:
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
                    # garantir tuplas de ints
                    self._mappings = {k: (int(v[0]), int(v[1])) for k, v in data.items()}
                print(f"Mapeamentos carregados de {self._mappings_file}")
            return True
        except Exception as e:
            print(f"Erro ao carregar mapeamentos: {e}")