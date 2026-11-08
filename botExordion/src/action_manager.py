"""Envio de input para a janela do jogo.

Todas as posições são relativas à área cliente da janela, então mover a janela
não invalida nada. Os métodos por mensagem funcionam com o jogo em segundo plano
e não mexem no cursor real.
"""
from __future__ import annotations

import contextlib
import ctypes
import logging
import threading
import time

import win32api
import win32con
import win32gui
import win32process

logger = logging.getLogger(__name__)

SEND_TIMEOUT_MS = 1000
GA_ROOT = 2
MOUSEEVENTF_MOVE = 0x0001
QUICK_PAUSE = 0.03  # uns dois quadros do cliente: menos que isso ele pode não ver o passo
QUICK_STEPS = 4
QUICK_DURATION = 0.04
MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}

VK_BY_NAME = {
    "enter": win32con.VK_RETURN,
    "space": win32con.VK_SPACE,
    "tab": win32con.VK_TAB,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "page_up": win32con.VK_PRIOR,
    "page_down": win32con.VK_NEXT,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "insert": win32con.VK_INSERT,
    "delete": win32con.VK_DELETE,
}
VK_BY_NAME.update({f"f{n}": win32con.VK_F1 + n - 1 for n in range(1, 13)})
EXTENDED_KEYS = {
    win32con.VK_UP, win32con.VK_DOWN, win32con.VK_LEFT, win32con.VK_RIGHT,
    win32con.VK_PRIOR, win32con.VK_NEXT, win32con.VK_HOME, win32con.VK_END,
    win32con.VK_INSERT, win32con.VK_DELETE,
}


def key_to_vk(name: str):
    name = str(name or "").strip().lower()
    if name in VK_BY_NAME:
        return VK_BY_NAME[name]
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(name.upper())
    return None


def make_lparam(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def set_user_input_blocked(blocked: bool) -> bool:
    """Bloqueia mouse e teclado físicos. Exige processo elevado."""
    try:
        block_input = ctypes.windll.user32.BlockInput
        block_input.argtypes = [ctypes.c_bool]
        block_input.restype = ctypes.c_bool
        return bool(block_input(blocked))
    except Exception:
        logger.exception("Erro ao alterar bloqueio do input")
        return False


class ActionManager:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        # Sequências de mouse de módulos diferentes não podem se misturar.
        self.lock = threading.RLock()

    # ---------- janela ----------

    def is_valid(self) -> bool:
        try:
            return bool(win32gui.IsWindow(self.hwnd))
        except Exception:
            return False

    def is_foreground(self) -> bool:
        return win32gui.GetForegroundWindow() == self.hwnd

    def is_minimized(self) -> bool:
        return bool(win32gui.IsIconic(self.hwnd))

    def title(self) -> str:
        try:
            return win32gui.GetWindowText(self.hwnd)
        except Exception:
            return ""

    def screen_to_client(self, pos):
        return win32gui.ScreenToClient(self.hwnd, (int(pos[0]), int(pos[1])))

    def client_to_screen(self, pos):
        return win32gui.ClientToScreen(self.hwnd, (int(pos[0]), int(pos[1])))

    def contains_screen_point(self, pos) -> bool:
        """True se o ponto da tela cai na janela do jogo, e não em outra por cima."""
        try:
            hit = win32gui.WindowFromPoint((int(pos[0]), int(pos[1])))
            return ctypes.windll.user32.GetAncestor(hit, GA_ROOT) == self.hwnd
        except Exception:
            return False

    def focusWindow(self) -> bool:
        try:
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.1)
            return True
        except Exception:
            logger.exception("Erro ao focar a janela")
            return False

    # ---------- exclusão mútua ----------

    @contextlib.contextmanager
    def guarded(self):
        """Reserva o mouse do jogo e bloqueia o input físico; devolve se conseguiu.

        O movimento real do mouse sobre o jogo chegaria ao cliente no meio da
        sequência e faria a ação acontecer na posição errada.
        """
        if not self.lock.acquire(timeout=1.5):
            yield False
            return
        blocked = False
        try:
            blocked = set_user_input_blocked(True)
            yield blocked
        finally:
            try:
                if blocked and not set_user_input_blocked(False):
                    logger.error("Falha ao liberar o input do usuário")
            finally:
                self.lock.release()

    # ---------- mouse por mensagem ----------

    def _send(self, message: int, wparam: int, lparam: int) -> None:
        win32gui.SendMessageTimeout(
            self.hwnd, message, wparam, lparam, win32con.SMTO_ABORTIFHUNG, SEND_TIMEOUT_MS
        )

    def _click(self, pos, down: int, up: int, button: int) -> bool:
        try:
            lparam = make_lparam(*pos)
            with self.lock:
                self._send(win32con.WM_MOUSEMOVE, 0, lparam)
                time.sleep(0.02)
                self._send(down, button, lparam)
                time.sleep(0.03)
                self._send(up, 0, lparam)
            return True
        except Exception as exc:
            logger.error("Erro no clique em %s: %s", pos, exc)
            return False

    def left_click(self, pos) -> bool:
        return self._click(pos, win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON)

    def right_click(self, pos) -> bool:
        return self._click(pos, win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON)

    def drag(self, start, end, steps: int = 12, duration: float = 0.2) -> bool:
        """Arrasta por mensagens, sem foco e sem mexer no cursor real."""
        sx, sy = int(start[0]), int(start[1])
        ex, ey = int(end[0]), int(end[1])
        pressed = False
        try:
            with self.lock:
                self._send(win32con.WM_MOUSEMOVE, 0, make_lparam(sx, sy))
                time.sleep(0.05)
                self._send(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, make_lparam(sx, sy))
                pressed = True
                time.sleep(0.08)
                for i in range(1, steps + 1):
                    x = int(sx + (ex - sx) * i / steps)
                    y = int(sy + (ey - sy) * i / steps)
                    self._send(win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, make_lparam(x, y))
                    time.sleep(max(0.008, duration / steps))
                time.sleep(0.05)
                self._send(win32con.WM_LBUTTONUP, 0, make_lparam(ex, ey))
                pressed = False
            return True
        except Exception as exc:
            logger.error("Erro durante o arrasto: %s", exc)
            return False
        finally:
            if pressed:  # nunca deixa o botão "preso" no cliente
                with contextlib.suppress(Exception):
                    self._send(win32con.WM_LBUTTONUP, 0, make_lparam(ex, ey))

    # ---------- mouse pelo cursor real (exige o jogo na frente) ----------

    @staticmethod
    def get_cursor():
        return win32api.GetCursorPos()

    @staticmethod
    def set_cursor(pos) -> None:
        ctypes.windll.user32.SetCursorPos(int(pos[0]), int(pos[1]))

    def click_with_cursor(self, pos, button: str) -> None:
        down, up = MOUSE_FLAGS[button]
        self.set_cursor(self.client_to_screen(pos))
        ctypes.windll.user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.mouse_event(up, 0, 0, 0, 0)

    def _move_cursor(self, x, y) -> None:
        # O cliente só atualiza a posição com um movimento de verdade.
        self.set_cursor((x, y))
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)

    def press_with_cursor(self, pos, button: str) -> None:
        """Clique em botão da interface, no ritmo do arrasto que o cliente aceita.

        O botão só reage se o cursor ainda estiver em cima dele ao soltar."""
        mouse_event = ctypes.windll.user32.mouse_event
        down, up = MOUSE_FLAGS[button]
        with self.lock:
            self._move_cursor(*self.client_to_screen(pos))
            time.sleep(0.08)
            mouse_event(down, 0, 0, 0, 0)
            try:
                time.sleep(0.10)
            finally:
                mouse_event(up, 0, 0, 0, 0)
            time.sleep(0.10)

    def drag_with_cursor(self, start, end, steps: int = 12, duration: float = 0.2, quick: bool = False) -> bool:
        """Plano B para clientes que leem o cursor real: traz o jogo para frente.

        quick corta as esperas para perto do que a macro de runa usa."""
        settle, hold, release = (QUICK_PAUSE,) * 3 if quick else (0.08, 0.10, 0.08)
        if quick:
            steps, duration = QUICK_STEPS, QUICK_DURATION
        mouse_event = ctypes.windll.user32.mouse_event
        left_down, left_up = MOUSE_FLAGS["left"]
        sx, sy = self.client_to_screen(start)
        ex, ey = self.client_to_screen(end)
        original = self.get_cursor()
        pressed = False
        try:
            with self.lock:
                if not (quick and self.is_foreground()):
                    self.focusWindow()
                self._move_cursor(sx, sy)
                time.sleep(settle)
                mouse_event(left_down, 0, 0, 0, 0)
                pressed = True
                time.sleep(hold)
                for i in range(1, steps + 1):
                    self._move_cursor(int(sx + (ex - sx) * i / steps), int(sy + (ey - sy) * i / steps))
                    time.sleep(max(0.008, duration / steps))
                time.sleep(release)
                mouse_event(left_up, 0, 0, 0, 0)
                pressed = False
                time.sleep(QUICK_PAUSE if quick else 0.10)
            return True
        except Exception as exc:
            logger.error("Erro durante o arrasto com cursor: %s", exc)
            return False
        finally:
            if pressed:
                mouse_event(left_up, 0, 0, 0, 0)
            self.set_cursor(original)

    # ---------- teclado ----------

    def _post_key(self, vk: int, down: bool) -> None:
        lparam = 1 | (win32api.MapVirtualKey(vk, 0) << 16)
        if vk in EXTENDED_KEYS:
            lparam |= 1 << 24
        if not down:
            lparam |= (1 << 30) | (1 << 31)
        win32api.PostMessage(self.hwnd, win32con.WM_KEYDOWN if down else win32con.WM_KEYUP, vk, lparam)

    def press_key(self, name: str) -> bool:
        vk = key_to_vk(name)
        if vk is None:
            logger.error("Tecla desconhecida: %r", name)
            return False
        try:
            self._post_key(vk, True)
            time.sleep(0.03)
            self._post_key(vk, False)
            return True
        except Exception as exc:
            logger.error("Erro ao enviar a tecla %s: %s", name, exc)
            return False

    def send_text(self, text: str) -> bool:
        """Digita no chat do jogo e confirma com Enter."""
        try:
            with self.lock:
                for char in text:
                    win32api.PostMessage(self.hwnd, win32con.WM_CHAR, ord(char), 1)
                    time.sleep(0.005)
                self._post_key(win32con.VK_RETURN, True)
                time.sleep(0.02)
                self._post_key(win32con.VK_RETURN, False)
            return True
        except Exception as exc:
            logger.error("Erro ao enviar texto: %s", exc)
            return False

    def turn(self, direction: str) -> bool:
        """Ctrl+seta. O cliente consulta o estado do Ctrl, e mensagem não o altera,
        então o estado é ajustado na fila de input da thread do jogo."""
        vk = key_to_vk(direction)
        user32 = ctypes.windll.user32
        current = win32api.GetCurrentThreadId()
        target, _ = win32process.GetWindowThreadProcessId(self.hwnd)
        attached = False
        state = (ctypes.c_ubyte * 256)()
        ctrl_before = None
        try:
            with self.lock:
                attached = bool(user32.AttachThreadInput(current, target, True))
                user32.GetKeyboardState(ctypes.byref(state))
                ctrl_before = state[win32con.VK_CONTROL]
                state[win32con.VK_CONTROL] = ctrl_before | 0x80
                user32.SetKeyboardState(ctypes.byref(state))
                self._post_key(win32con.VK_CONTROL, True)
                self._post_key(vk, True)
                time.sleep(0.05)
                self._post_key(vk, False)
                self._post_key(win32con.VK_CONTROL, False)
                time.sleep(0.05)
            return True
        except Exception as exc:
            logger.error("Erro ao virar o personagem: %s", exc)
            return False
        finally:
            if ctrl_before is not None:
                state[win32con.VK_CONTROL] = ctrl_before
                user32.SetKeyboardState(ctypes.byref(state))
            if attached:
                user32.AttachThreadInput(current, target, False)
