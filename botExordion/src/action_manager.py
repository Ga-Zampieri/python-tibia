import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except AttributeError:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        pass
import win32api
import win32con
import win32gui
import time
import logging
left_mouse_down = 0x01
right_mouse_down = 0x02

class ActionManager:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

    def left_click(self, pos):
        while (win32api.GetKeyState(win32con.VK_CONTROL) < 0 or
            win32api.GetKeyState(win32con.VK_SHIFT) < 0 or
            win32api.GetKeyState(win32con.VK_MENU) < 0 or
            win32api.GetKeyState(left_mouse_down) < 0 or
            win32api.GetKeyState(right_mouse_down) < 0):
            time.sleep(0.005)

        client_pos = win32gui.ScreenToClient(self.hwnd, (pos[0], pos[1]))
        LongPositionToClick = win32api.MAKELONG(client_pos[0], client_pos[1])
        win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.VK_LBUTTON, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONUP, win32con.VK_LBUTTON, LongPositionToClick)
        return True

    def right_click(self, pos):
        while (win32api.GetKeyState(win32con.VK_CONTROL) < 0 or
            win32api.GetKeyState(win32con.VK_SHIFT) < 0 or
            win32api.GetKeyState(win32con.VK_MENU) < 0 or
            win32api.GetKeyState(left_mouse_down) < 0 or
            win32api.GetKeyState(right_mouse_down) < 0):
            time.sleep(0.005)
        
        client_pos = win32gui.ScreenToClient(self.hwnd, (pos[0], pos[1]))
        LongPositionToClick = win32api.MAKELONG(client_pos[0], client_pos[1])
        win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_RBUTTONDOWN, win32con.VK_RBUTTON, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, LongPositionToClick)
        win32api.SendMessage(self.hwnd, win32con.WM_RBUTTONUP, win32con.VK_RBUTTON, LongPositionToClick)
        return True

    def get_cursor_position(self):
        try:
            x, y = win32api.GetCursorPos()
            return x, y
        except Exception as e:
            self.logger.error(f"Erro ao obter posição do cursor: {e}")
            return (0, 0)

    def move_mouse(self, pos):
        while (win32api.GetKeyState(win32con.VK_CONTROL) < 0 or
            win32api.GetKeyState(win32con.VK_SHIFT) < 0 or
            win32api.GetKeyState(win32con.VK_MENU) < 0 or
            win32api.GetKeyState(left_mouse_down) < 0 or
            win32api.GetKeyState(right_mouse_down) < 0):
            time.sleep(0.005)
        client_pos = win32gui.ScreenToClient(self.hwnd, (pos[0], pos[1]))
        LongPositionToClick = win32api.MAKELONG(client_pos[0], client_pos[1])
        win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, LongPositionToClick)

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