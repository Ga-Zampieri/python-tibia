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
        self._player_position = None
        self._self_use_mappings = {}
        self._push_item_mappings = {}
        self._drag_end_mappings = {}
        self._mappings_file = os.path.join(os.path.dirname(__file__), "../assets/runa_mappings.json")
        self._action_lock = threading.Lock()
        self.status = Status.Inactive

    # ---------- helpers de input ----------

    @staticmethod
    def _set_cursor_pos(x: int, y: int) -> bool:
        try:
            import ctypes
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
            return True
        except Exception:
            return False

    @staticmethod
    def _nudge_cursor() -> None:
        """Gera dois eventos de mouse move (1px dir, 1px esq) para forçar o game a registrar."""
        try:
            import ctypes
            ctypes.windll.user32.mouse_event(0x0001, 1, 0, 0, 0)
            ctypes.windll.user32.mouse_event(0x0001, -1, 0, 0, 0)
        except Exception:
            pass

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
    def _set_user_input_blocked(blocked: bool) -> bool:
        try:
            import ctypes
            block_input = ctypes.windll.user32.BlockInput
            block_input.argtypes = [ctypes.c_bool]
            block_input.restype = ctypes.c_bool
            return bool(block_input(blocked))
        except Exception as e:
            print(f"Erro ao alterar bloqueio do input: {e}")
            return False

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

    @staticmethod
    def _send_left_click():
        try:
            import ctypes
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            sleep(0.02)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception as e:
            print(f"Erro ao enviar clique esquerdo: {e}")

    @staticmethod
    def _send_left_down():
        try:
            import ctypes
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        except Exception as e:
            print(f"Erro ao enviar left down: {e}")

    @staticmethod
    def _send_left_up():
        try:
            import ctypes
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        except Exception as e:
            print(f"Erro ao enviar left up: {e}")

    # ---------- drag (push item) ----------

    def _drag(self, start, end, steps: int = 12, duration: float = 0.2) -> bool:
        """Drag-and-drop: cursor para start, left down, interpola até end, left up."""
        try:
            sx, sy = int(start[0]), int(start[1])
            ex, ey = int(end[0]), int(end[1])

            if not self._set_cursor_pos(sx, sy):
                print("Drag: falha ao mover cursor para o ponto inicial.")
                return False
            self._nudge_cursor()
            sleep(0.08)

            self._send_left_down()
            sleep(0.10)

            for i in range(1, steps + 1):
                t = i / steps
                x = int(sx + (ex - sx) * t)
                y = int(sy + (ey - sy) * t)
                self._set_cursor_pos(x, y)
                self._nudge_cursor()
                sleep(max(0.008, duration / steps))

            sleep(0.08)
            self._send_left_up()
            sleep(0.10)
            return True
        except Exception as e:
            print(f"Erro durante o drag: {e}")
            try:
                self._send_left_up()
            except Exception:
                pass
            return False

    def _execute_push_item(self, key_name: str) -> bool:
        start = self._mappings.get(key_name)
        end = self._drag_end_mappings.get(key_name)
        if not start:
            print(f"Push item: ponto inicial não configurado para '{key_name}'.")
            return False
        if not end:
            print(f"Push item: ponto final não configurado para '{key_name}'.")
            return False

        if not self._action_lock.acquire(blocking=False):
            print("Ação já em progresso. Ignorando push item.")
            return False

        start_cursor = None
        input_blocked = False
        try:
            input_blocked = self._set_user_input_blocked(True)
            if not input_blocked:
                print("Push item: não foi possível bloquear o input (precisa de admin). Ação cancelada.")
                return False

            if self._action_manager and hasattr(self._action_manager, "focusWindow"):
                try:
                    self._action_manager.focusWindow()
                except Exception:
                    pass

            start_cursor = self._get_cursor_pos()
            return self._drag(start, end)
        finally:
            try:
                if start_cursor and start_cursor[0] is not None:
                    self._set_cursor_pos(start_cursor[0], start_cursor[1])
            finally:
                try:
                    if input_blocked:
                        self._set_user_input_blocked(False)
                finally:
                    self._action_lock.release()

    # ---------- rune use (comportamento original) ----------

    def _execute_rune_use(self, key_name: str) -> bool:
        coords = self._mappings.get(key_name)
        if not coords:
            print(f"Nenhuma runa mapeada para a tecla '{key_name}'.")
            return False

        targetX, targetY = coords
        self_use = self._self_use_mappings.get(key_name, False)
        player_coords = self._player_position
        if self_use and not player_coords:
            print(f"Nenhuma coordenada do player mapeada para a tecla '{key_name}'.")
            return False

        if not self._action_lock.acquire(blocking=False):
            print("Ação já em progresso. Ignorando novo pedido.")
            return False

        startX = startY = None
        input_blocked = False
        try:
            input_blocked = self._set_user_input_blocked(True)
            if not input_blocked:
                print("Não foi possível bloquear o input. Execute como administrador; ação cancelada.")
                return False

            startX, startY = self._get_cursor_pos()
            if not self._set_cursor_pos(targetX, targetY):
                print("Falha ao mover o cursor para a posição da runa.")
                return False

            self._send_right_click()
            sleep(0.05)

            if self_use:
                if not self._set_cursor_pos(*player_coords):
                    print("Falha ao mover o cursor para a posição do player.")
                    return False
                self._send_left_click()

            return True
        except Exception as e:
            print(f"Erro durante equipagem da runa: {e}")
            return False
        finally:
            try:
                if startX is not None and startY is not None:
                    self._set_cursor_pos(startX, startY)
            finally:
                try:
                    if input_blocked and not self._set_user_input_blocked(False):
                        print("Falha ao liberar o input do usuário.")
                finally:
                    self._action_lock.release()

    def equipRuna(self, key_name: str = None) -> bool:
        if not key_name:
            print("É necessário especificar a hotkey.")
            return False
        if self.is_push_item_enabled(key_name):
            return self._execute_push_item(key_name)
        return self._execute_rune_use(key_name)

    # ---------- ataque / thread principal ----------

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

    # ---------- captura de pontos ----------

    def getRuna(self, key_name: str = None, timeout: int = 10):
        """Captura 1 clique (ponto da runa)."""
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False
        try:
            coords = {}
            print("Clique na runa no inventário...")
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)
            listener.stop()
            if 'x' in coords:
                if key_name:
                    self.map_key_to_coords(key_name, coords['x'], coords['y'])
                    return True
                print("Necessário informar uma hotkey para bindar a runa capturada.")
                return False
            print("Nenhuma coordenada registrada (timeout).")
            return False
        except Exception as e:
            print(f"Erro ao localizar runa: {e}")
            return False

    def getDragPoints(self, key_name: str = None, timeout: int = 20):
        """Captura 2 cliques (início e fim do drag)."""
        points = []

        def _on_click(x, y, button, pressed):
            if pressed:
                points.append((int(x), int(y)))
                print(f"Ponto {len(points)}/2 do drag: ({x}, {y})")
                if len(points) >= 2:
                    return False

        try:
            print("Ponto 1/2: clique no INÍCIO do drag (botão esquerdo)...")
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)
            listener.stop()

            if len(points) >= 2:
                if not key_name:
                    print("Necessário informar uma hotkey para o drag.")
                    return False
                self.map_key_to_coords(key_name, points[0][0], points[0][1])
                self._drag_end_mappings[key_name] = points[1]
                print(f"Drag mapeado: '{key_name}' -> {points[0]} até {points[1]}")
                return True
            print(f"Esperados 2 cliques, recebidos {len(points)}.")
            return False
        except Exception as e:
            print(f"Erro ao capturar drag: {e}")
            return False

    def getPlayerPosition(self, timeout: int = 10):
        coords = {}

        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False

        try:
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)
            listener.stop()
            if 'x' not in coords:
                print("Nenhuma coordenada do player registrada (timeout).")
                return False
            self.set_player_position(coords['x'], coords['y'])
            return True
        except Exception as e:
            print(f"Erro ao capturar a posição do player: {e}")
            return False

    # ---------- mapeamentos ----------

    def map_key_to_coords(self, key_name: str, x: int, y: int):
        self._mappings[key_name] = (int(x), int(y))
        print(f"Mapeado: '{key_name}' -> ({x}, {y})")

    def set_player_position(self, x: int, y: int):
        self._player_position = (int(x), int(y))
        print(f"Posição do player salva -> ({x}, {y})")

    def set_self_use(self, key_name: str, enabled: bool):
        if key_name:
            if enabled:
                self._push_item_mappings[key_name] = False
            self._self_use_mappings[key_name] = bool(enabled)

    def is_self_use_enabled(self, key_name: str) -> bool:
        return self._self_use_mappings.get(key_name, False)

    def set_push_item(self, key_name: str, enabled: bool):
        if key_name:
            if enabled:
                self._self_use_mappings[key_name] = False
            self._push_item_mappings[key_name] = bool(enabled)

    def is_push_item_enabled(self, key_name: str) -> bool:
        return self._push_item_mappings.get(key_name, False)

    def remove_mapping(self, key_name: str):
        if key_name in self._mappings or key_name in self._self_use_mappings or key_name in self._push_item_mappings:
            self._mappings.pop(key_name, None)
            self._self_use_mappings.pop(key_name, None)
            self._push_item_mappings.pop(key_name, None)
            self._drag_end_mappings.pop(key_name, None)
            print(f"Removido mapeamento para '{key_name}'")
        else:
            print(f"Nenhum mapeamento encontrado para '{key_name}'")

    def list_mappings(self):
        if not self._mappings:
            print("Nenhum mapeamento de runa definido.")
            return
        print("Mapeamentos atuais:")
        print(f"  Posição global do player: {self._player_position}")
        for k, v in self._mappings.items():
            if self.is_push_item_enabled(k):
                end = self._drag_end_mappings.get(k)
                print(f"  '{k}' -> DRAG {v} -> {end}")
            else:
                mode = "self use" if self.is_self_use_enabled(k) else "normal"
                print(f"  '{k}' -> X {v[0]}, Y {v[1]} | modo: {mode}")

    def resetRuna(self, key_name: str = None):
        if key_name:
            self.remove_mapping(key_name)
        else:
            self._mappings = {}
            self._player_position = None
            self._self_use_mappings = {}
            self._push_item_mappings = {}
            self._drag_end_mappings = {}

    # ---------- persistência ----------

    def save_mappings(self):
        try:
            os.makedirs(os.path.dirname(self._mappings_file), exist_ok=True)
            mappings = {}
            for key in self._mappings:
                mappings[key] = {
                    "rune": list(self._mappings[key]),
                    "self_use": bool(self._self_use_mappings.get(key, False)),
                    "push_item": bool(self._push_item_mappings.get(key, False)),
                    "drag_end": (
                        list(self._drag_end_mappings[key])
                        if key in self._drag_end_mappings
                        else None
                    ),
                }
            data = {
                "player_position": list(self._player_position) if self._player_position else None,
                "mappings": mappings,
            }
            with open(self._mappings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Mapeamentos salvos em {self._mappings_file}")
            return True
        except Exception as e:
            print(f"Erro ao salvar mapeamentos: {e}")
            return False

    def load_mappings(self, merge_existing: bool = False):
        try:
            if not os.path.exists(self._mappings_file):
                return True

            current_mappings = self._mappings.copy() if merge_existing else {}
            current_player_position = self._player_position if merge_existing else None
            current_self = self._self_use_mappings.copy() if merge_existing else {}
            current_push = self._push_item_mappings.copy() if merge_existing else {}
            current_drag = self._drag_end_mappings.copy() if merge_existing else {}

            with open(self._mappings_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._mappings = {}
            self._player_position = None
            self._self_use_mappings = {}
            self._push_item_mappings = {}
            self._drag_end_mappings = {}

            if isinstance(data.get("mappings"), dict):
                mappings = data["mappings"]
                pp = data.get("player_position")
                if pp is not None:
                    self._player_position = (int(pp[0]), int(pp[1]))
            else:
                mappings = data

            for key, value in mappings.items():
                if isinstance(value, dict):
                    rune_coords = value.get("rune")
                    if rune_coords is not None:
                        self._mappings[key] = (int(rune_coords[0]), int(rune_coords[1]))
                    self._self_use_mappings[key] = bool(value.get("self_use", False))
                    self._push_item_mappings[key] = bool(value.get("push_item", False))
                    drag_end = value.get("drag_end")
                    if drag_end is not None:
                        self._drag_end_mappings[key] = (int(drag_end[0]), int(drag_end[1]))
                else:
                    self._mappings[key] = (int(value[0]), int(value[1]))

            # Impede estado inválido de JSON antigo (self_use + push_item ao mesmo tempo)
            for k in set(self._self_use_mappings) | set(self._push_item_mappings):
                if self._self_use_mappings.get(k) and self._push_item_mappings.get(k):
                    self._push_item_mappings[k] = False

            self._mappings.update(current_mappings)
            if current_player_position is not None:
                self._player_position = current_player_position
            self._self_use_mappings.update(current_self)
            self._push_item_mappings.update(current_push)
            self._drag_end_mappings.update(current_drag)

            print(f"Mapeamentos carregados de {self._mappings_file}")
            return True
        except Exception as e:
            print(f"Erro ao carregar mapeamentos: {e}")
            return False