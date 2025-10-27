import random
import pyautogui as pgui
from pynput import mouse, keyboard
import threading
import time
import json
import os

class Runa:
    _thread = None
    _stop_event = threading.Event()
    _kb_listener = None
    runaX = None
    runaY = None
    # mapa: nome_da_tecla -> (x, y)
    _mappings = {}
    _mappings_file = os.path.join(os.path.dirname(__file__), "runa_mappings.json")

    # ...existing code...
    @classmethod
    def _key_to_name(cls, key):
        """Normaliza um objeto Key/KeyCode para string (ex: 'f1', 'a', 'esc')."""
        try:
            # KeyCode (letras/teclas imprimíveis)
            if hasattr(key, "char") and key.char is not None:
                return key.char.lower()
        except Exception:
            pass
        # Key especial (Key.f1) -> 'f1'
        return str(key).split('.')[-1]

    @classmethod
    def _on_key_press(cls, key):
        try:
            name = cls._key_to_name(key)
            if name == "esc":
                cls._stop_event.set()
                return
            # se existir mapeamento para a tecla, equipar a runa correspondente
            if name in cls._mappings:
                try:
                    cls.equipRuna(name)
                except Exception as e:
                    print(f"Erro ao tentar equipar runa ({name}): {e}")
        except Exception:
            pass

    @classmethod
    def equipRuna(cls, key_name: str = None):
        """Move o mouse e clica na runa mapeada pela tecla (ou usa runaX/runaY padrão).

        Se key_name for fornecido, busca as coordenadas em _mappings.
        """
        if key_name:
            coords = cls._mappings.get(key_name)
            if not coords:
                print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
                return
            targetX, targetY = coords
        else:
            if cls.runaX is None or cls.runaY is None:
                print("Coordenadas da runa não definidas. Aguarde e clique na runa para registrar...")
                ok = cls.getRuna()
                if not ok or cls.runaX is None or cls.runaY is None:
                    print("Falha ao obter coordenadas da runa. Operação cancelada.")
                    return
            targetX, targetY = cls.runaX, cls.runaY

        try:
            currentX, currentY = pgui.position().x, pgui.position().y
            pgui.moveTo(targetX, targetY)
            pgui.click(button='right')
            pgui.moveTo(currentX, currentY)
        except Exception as e:
            print(f"Erro durante o clique na runa: {e}")

    @classmethod
    def Atacar(cls, status: bool):
        if status:
            if cls._thread and cls._thread.is_alive():
                return  # já rodando
            if cls._kb_listener is None or not getattr(cls._kb_listener, "is_alive", lambda: False)():
                cls._kb_listener = keyboard.Listener(on_press=cls._on_key_press)
                cls._kb_listener.daemon = True
                cls._kb_listener.start()
            cls._stop_event.clear()
        else:
            cls._stop_event.set()
            try:
                if cls._kb_listener is not None:
                    cls._kb_listener.stop()
            except Exception:
                pass
            cls._kb_listener = None

    @classmethod
    def getRuna(cls, key_name: str = None, timeout: int = 10):
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
                    cls._mappings[key_name] = (coords['x'], coords['y'])
                    print(f"Runa mapeada: tecla '{key_name}' -> X {coords['x']}, Y {coords['y']}")
                else:
                    cls.runaX, cls.runaY = coords['x'], coords['y']
                    print(f"Runa padrão encontrada em: X {cls.runaX}, Y {cls.runaY}")
                return True
            else:
                print("Nenhuma coordenada registrada (timeout).")
                return False
        except Exception as e:
            print(f"Erro ao localizar runa: {e}")
        finally:
            pass

    @classmethod
    def map_key_to_coords(cls, key_name: str, x: int, y: int):
        cls._mappings[key_name] = (int(x), int(y))
        print(f"Mapeado: '{key_name}' -> ({x}, {y})")

    @classmethod
    def remove_mapping(cls, key_name: str):
        if key_name in cls._mappings:
            del cls._mappings[key_name]
            print(f"Removido mapeamento para '{key_name}'")
        else:
            print(f"Nenhum mapeamento encontrado para '{key_name}'")

    @classmethod
    def list_mappings(cls):
        if not cls._mappings:
            print("Nenhum mapeamento de runa definido.")
            return
        print("Mapeamentos atuais:")
        for k, v in cls._mappings.items():
            print(f"  '{k}' -> X {v[0]}, Y {v[1]}")

    @classmethod
    def resetRuna(cls, key_name: str = None):
        if key_name:
            cls.remove_mapping(key_name)
        else:
            cls.runaX = None
            cls.runaY = None
            print("Coordenadas de runa padrão foram resetadas.")

    @classmethod
    def save_mappings(cls):
        try:
            with open(cls._mappings_file, "w", encoding="utf-8") as f:
                json.dump(cls._mappings, f, ensure_ascii=False, indent=2)
            print(f"Mapeamentos salvos em {cls._mappings_file}")
        except Exception as e:
            print(f"Erro ao salvar mapeamentos: {e}")

    @classmethod
    def load_mappings(cls):
        try:
            if os.path.exists(cls._mappings_file):
                with open(cls._mappings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # garantir tuplas de ints
                    cls._mappings = {k: (int(v[0]), int(v[1])) for k, v in data.items()}
                print(f"Mapeamentos carregados de {cls._mappings_file}")
        except Exception as e:
            print(f"Erro ao carregar mapeamentos: {e}")