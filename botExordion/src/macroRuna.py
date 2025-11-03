from pynput import mouse, keyboard
import threading
import time
import os
import json
import ctypes
import platform
import time
from ctypes import wintypes

class Runa:
    _thread = None
    _stop_event = threading.Event()
    _kb_listener = None
    # mapa: nome_da_tecla -> (x, y)
    _mappings = {}
    _mappings_file = os.path.join(os.path.dirname(__file__), "../assets/runa_mappings.json")
    # evita executar duas equipRuna simultâneas
    _action_lock = threading.Lock()


    @staticmethod
    def _set_cursor_pos(x: int, y: int) -> bool:
        """Move o cursor diretamente via Windows API."""
        if platform.system() != "Windows":
            return False
        try:
            return ctypes.windll.user32.SetCursorPos(x, y)
        except:
            return False

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

    @staticmethod
    def _get_cursor_pos():
        """Retorna (x,y) atual do cursor via GetCursorPos."""
        pt = wintypes.POINT()
        try:
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        except Exception:
            return None, None


    @staticmethod
    def _send_right_click():
        """Enviar RIGHTDOWN e RIGHTUP separadamente, com pequeno delay entre eles."""
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG),
                        ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]

        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD),
                        ("ii", _INPUT_UNION)]

        try:
            SendInput = ctypes.windll.user32.SendInput
        except Exception:
            # fallback simples
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(0.02)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return

        # RIGHTDOWN
        inp = INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.ii.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, None)
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        # breve pausa para garantir o sistema processe o down enquanto o cursor está no alvo
        time.sleep(0.02)

        # RIGHTUP
        inp_up = INPUT()
        inp_up.type = 0
        inp_up.ii.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, None)
        SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

        # pequena pausa para garantir processamento do clique antes de mover o cursor
        time.sleep(0.02)

    @staticmethod
    def _wait_for_cursor(x: int, y: int, timeout: float = 0.5, interval: float = 0.005) -> bool:
        """Aguarda até o cursor estar exatamente em (x,y) ou timeout expirar."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            cx, cy = Runa._get_cursor_pos()
            if cx == x and cy == y:
                return True
            time.sleep(interval)
        return False
    
    @classmethod
    def equipRuna(cls, key_name: str = None) -> bool:
        """Mover → esperar chegada (obrigatório) → 1x clique direito → voltar.

        Se o cursor não atingir a posição alvo dentro do timeout, a ação é abortada
        e nenhum clique é enviado.
        """
        if not key_name:
            print("É necessário especificar a hotkey.")
            return False

        coords = cls._mappings.get(key_name)
        if not coords:
            print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
            return False
        targetX, targetY = int(coords[0]), int(coords[1])

        # evita concorrência
        if not cls._action_lock.acquire(blocking=False):
            print("Ação já em progresso. Ignorando novo pedido.")
            return False

        try:
            # captura posição inicial
            start = cls._get_cursor_pos()
            startX, startY = (None, None) if start is None else start

            # 1) mover para o alvo (set + confirma)
            cls._set_cursor_pos(targetX, targetY)

            # 2) aguardar confirmação obrigatória de chegada (até 100ms)
            deadline = time.monotonic() + 0.100
            arrived = False
            while time.monotonic() < deadline:
                cx, cy = cls._get_cursor_pos()
                if cx == targetX and cy == targetY:
                    arrived = True
                    break
                # reforçar a posição rapidamente
                cls._set_cursor_pos(targetX, targetY)
                time.sleep(0.005)

            if not arrived:
                print("Abortado: cursor não alcançou o destino dentro do timeout. Nenhum clique enviado.")
                return False

            cls._send_right_click()

            # garantir que o cursor ainda esteja no alvo (espera curta); se não, não mover de volta até confirmar
            # (máx 50ms)
            if not cls._wait_for_cursor(targetX, targetY, timeout=0.05, interval=0.003):
                # reforça posição e aguarda mais um pouco
                cls._set_cursor_pos(targetX, targetY)
                cls._wait_for_cursor(targetX, targetY, timeout=0.05, interval=0.003)

            # 5) voltar à posição inicial (se conhecida) e confirmar (até 100ms)
            if startX is not None and startY is not None:
                cls._set_cursor_pos(startX, startY)
                deadline = time.monotonic() + 0.100
                while time.monotonic() < deadline:
                    cx, cy = cls._get_cursor_pos()
                    if cx == startX and cy == startY:
                        break
                    cls._set_cursor_pos(startX, startY)
                    time.sleep(0.005)

            return True
        except Exception as e:
            print(f"Erro durante equipagem da runa: {e}")
            return False
        finally:
            cls._action_lock.release()

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
                    cls.map_key_to_coords(key_name, coords['x'], coords['y'])
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
        return True

    @classmethod
    def resetRuna(cls, key_name: str = None):
        if key_name:
            cls.remove_mapping(key_name)
        else:
            cls._mappings = {}

    @classmethod
    def save_mappings(cls):
        try:
            with open(cls._mappings_file, "w", encoding="utf-8") as f:
                json.dump(cls._mappings, f, ensure_ascii=False, indent=2)
            print(f"Mapeamentos salvos em {cls._mappings_file}")
            return True 
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
            return True
        except Exception as e:
            print(f"Erro ao carregar mapeamentos: {e}")