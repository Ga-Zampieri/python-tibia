import win32api
import win32con
import win32gui
import time
import logging


class ActionManager:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        # Configura logging básico
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)
        
    def _make_lparam(self, x: int, y: int) -> int:
        """
        Combina coordenadas x,y em um LPARAM para mensagens de mouse do Windows.
        x vai para os 16 bits menos significativos
        y vai para os 16 bits mais significativos
        """
        try:
            return (y << 16) | (x & 0xFFFF)
        except Exception as e:
            self.logger.error(f"Erro ao criar LPARAM: {e}")
            return 0

    def left_click(self, pos):
        try:
            x, y = pos
            # Convert screen to client coordinates
            client_x, client_y = win32gui.ScreenToClient(self.hwnd, (x, y))
            # Create proper lparam from client coordinates
            lparam = self._make_lparam(client_x, client_y)
            self.logger.debug(f"Enviando left click para posição ({x}, {y}) -> client({client_x}, {client_y})")
            
            # Move mouse first
            win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            time.sleep(0.02)  # small delay to ensure move is processed
            
            # Click down with proper button state in wParam
            win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONDOWN, 
                                win32con.MK_LBUTTON, lparam)
            time.sleep(0.03)  # minimal delay between down/up
            
            # Click up (no button state in wParam for up)
            win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            return True
        except Exception as e:
            self.logger.error(f"Erro no left_click: {e}")
            return False

    def right_click(self, pos):
        try:
            x, y = pos
            # Convert screen to client coordinates
            client_x, client_y = win32gui.ScreenToClient(self.hwnd, (x, y))
            # Create proper lparam from client coordinates
            lparam = self._make_lparam(client_x, client_y)
            self.logger.debug(f"Enviando right click para posição ({x}, {y}) -> client({client_x}, {client_y})")
            
            # Move mouse first
            win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            time.sleep(0.02)  # small delay to ensure move is processed
            
            # Click down with proper button state in wParam
            win32api.SendMessage(self.hwnd, win32con.WM_RBUTTONDOWN, 
                                win32con.MK_RBUTTON, lparam)
            time.sleep(0.03)  # minimal delay between down/up
            
            # Click up (no button state in wParam for up)
            win32api.SendMessage(self.hwnd, win32con.WM_RBUTTONUP, 0, lparam)
            return True
        except Exception as e:
            self.logger.error(f"Erro no right_click: {e}")
            return False

    def get_cursor_position(self):
        try:
            x, y = win32api.GetCursorPos()
            return x, y
        except Exception as e:
            self.logger.error(f"Erro ao obter posição do cursor: {e}")
            return (0, 0)

    def move_mouse(self, pos):
        try:
            x, y = int(pos[0]), int(pos[1])
            client_pos = win32gui.ScreenToClient(self.hwnd, (x, y))
            # Create proper lparam from client coordinates
            lparam = self._make_lparam(client_pos[0], client_pos[1])
            # Send mouse move message with proper lparam
            win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            self.logger.info(f"Movendo mouse virtual para posição: {client_pos}")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao mover mouse: {e}")
            return False

    def focusWindow(self):
        try:
            if not win32gui.IsWindow(self.hwnd):
                self.logger.error("HWND inválido")
                return False
                
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.1)
            return True
        except Exception as e:
            self.logger.error(f"Erro ao focar janela: {e}")
            return False

    def send_key(self, key: str):
        try:
            win32api.keybd_event(ord(key.upper()), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord(key.upper()), 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            self.logger.error(f"Erro ao enviar tecla {key}: {e}")
            return False

    def is_valid(self):
        """Verifica se o HWND ainda é válido"""
        try:
            return bool(win32gui.IsWindow(self.hwnd))
        except:
            return False