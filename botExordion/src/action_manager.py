"""Envio de input para a janela do jogo.

Todas as posições são relativas à área cliente da janela, então mover a janela
não invalida nada. Os métodos por mensagem funcionam com o jogo em segundo plano
e não mexem no cursor real.
"""
from __future__ import annotations

import contextlib
import ctypes
import heapq
import itertools
import logging
import threading
import time

import win32api
import win32con
import win32gui
import win32process

logger = logging.getLogger(__name__)

SEND_TIMEOUT_MS = 1000
GUARD_TIMEOUT = 1.5
# Quem passa na frente quando dois módulos querem o mouse ao mesmo tempo.
PRIORITIES = {"heal": 0, "macro": 1, "loot": 2, "repeater": 3, "normal": 4, "rune_maker": 5, "fishing": 6}
LLMHF_ANY_INJECTED = 0x1 | 0x2
MOUSE_UP_FLAGS = {0x0202: 0x0004, 0x0205: 0x0010, 0x0208: 0x0040}  # mensagem do soltar -> mouse_event
DEFAULT_INPUT = {"pause_ms": 30, "server_wait": 2.0, "diagnostic": False}
GA_ROOT = 2
MOUSEEVENTF_MOVE = 0x0001
QUICK_PAUSE = 0.03  # uns dois quadros do cliente: menos que isso ele pode não ver o passo
QUICK_STEPS = 4
QUICK_DURATION = 0.04
# O cliente pode ler o botão e a posição um ou dois quadros depois: antes disso o
# cursor não volta para onde estava, senão o item cai lá.
DROP_GRACE = 0.08
QUICK_MIN_STEP = 0.05  # o aperto precisa ser visto ainda em cima do item
MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
# Teclado inteiro, sem os botões do mouse (1 a 6), sem Shift/Ctrl/Alt genéricos, que o
# Windows já informa pelos lados esquerdo e direito, e sem a tecla Windows, que abriria o Iniciar.
KEYBOARD_VKS = tuple(vk for vk in range(0x08, 0xFF) if vk not in (0x10, 0x11, 0x12, 0x5B, 0x5C))
RIGHT_SIDE_MODIFIERS = {0xA3, 0xA5}  # Ctrl e Alt da direita são teclas estendidas

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


_local = threading.local()


@contextlib.contextmanager
def priority(level: str):
    """Marca as ações desta thread com uma prioridade de PRIORITIES."""
    previous = getattr(_local, "level", "normal")
    _local.level = level
    try:
        yield
    finally:
        _local.level = previous


def current_priority() -> int:
    return PRIORITIES[getattr(_local, "level", "normal")]


class PriorityLock:
    """Lock reentrante em que, havendo fila, o pedido mais urgente entra primeiro.

    A cura não pode esperar o loot terminar uma coleta inteira: assim ela entra
    logo depois do arraste que estiver acontecendo."""

    def __init__(self):
        self._condition = threading.Condition()
        self._owner = None
        self._depth = 0
        self._waiting = []
        self._tickets = itertools.count()

    def acquire(self, blocking: bool = True, timeout=None) -> bool:
        me = threading.get_ident()
        with self._condition:
            if self._owner == me:
                self._depth += 1
                return True
            ticket = (current_priority(), next(self._tickets))
            heapq.heappush(self._waiting, ticket)
            deadline = None if timeout is None or timeout < 0 else time.monotonic() + timeout
            try:
                while self._owner is not None or self._waiting[0] != ticket:
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if not blocking or (remaining is not None and remaining <= 0):
                        self._waiting.remove(ticket)
                        heapq.heapify(self._waiting)
                        self._condition.notify_all()
                        return False
                    self._condition.wait(remaining)
            except BaseException:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                    heapq.heapify(self._waiting)
                    self._condition.notify_all()
                raise
            heapq.heappop(self._waiting)
            self._owner, self._depth = me, 1
            return True

    def release(self) -> None:
        with self._condition:
            if self._owner != threading.get_ident():
                raise RuntimeError("release de um lock que esta thread não tem")
            self._depth -= 1
            if self._depth == 0:
                self._owner = None
                self._condition.notify_all()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_exc):
        self.release()


class MouseBlocker:
    """Segura só o mouse físico enquanto o bot age.

    O teclado continua livre (nenhuma tecla fica presa) e não precisa de
    administrador. O input do próprio bot passa, porque vem marcado como injetado."""

    def __init__(self):
        self._listener = None
        self._swallowed = set()

    def start(self) -> bool:
        try:
            from pynput import mouse
            swallowed = self._swallowed = set()
            listener = None

            def only_ours(msg, data):
                if data.flags & LLMHF_ANY_INJECTED:
                    return True
                if msg in MOUSE_UP_FLAGS:
                    swallowed.add(MOUSE_UP_FLAGS[msg])
                listener.suppress_event()

            listener = mouse.Listener(win32_event_filter=only_ours)
            listener.start()
            listener.wait()
            if not listener.running:
                listener.stop()
                return False
            self._listener = listener
            return True
        except Exception:
            logger.exception("Não deu para segurar o mouse")
            return False

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        # Quem soltou o botão durante a ação: o soltar acontece agora.
        for flag in self._swallowed:
            ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)
        self._swallowed = set()


def use_messages(am, background: bool) -> bool:
    """Mensagem não mexe no cursor nem precisa de foco, mas com o jogo na frente
    o cliente pode lê-la errado: por isso só vale com o jogo atrás."""
    return background and not am.is_foreground()


def _diagnose(am, what: str, messages: bool, action):
    started = time.monotonic()
    result = action()
    if am.diagnostic:
        logger.info("Input: %s por %s em %.0f ms -> %s", what, "mensagem" if messages else "cursor",
                    (time.monotonic() - started) * 1000, "ok" if result is not False else "falhou")
    return result


def click_item(am, pos, button: str, background: bool = True, interface: bool = False) -> bool:
    """Clique pelo caminho certo. interface=True é para botões (X, seta), que
    só reagem com o cursor parado em cima ao soltar."""
    if use_messages(am, background):
        click = am.right_click if button == "right" else am.left_click
        return _diagnose(am, f"clique {button} {tuple(pos)}", True, lambda: click(pos))

    def with_cursor():
        original = am.get_cursor()
        try:
            (am.press_with_cursor if interface else am.click_with_cursor)(pos, button)
            return True
        finally:
            am.set_cursor(original)
    return _diagnose(am, f"clique {button} {tuple(pos)}", False, with_cursor)


def drag_item(am, start, end, background: bool, quick: bool = False) -> bool:
    """Arrasta pelo caminho que o cliente aceita (ver use_messages)."""
    messages = use_messages(am, background)
    what = f"arraste {tuple(start)} -> {tuple(end)}"
    if messages:
        return _diagnose(am, what, True, lambda: am.drag(start, end, quick=quick))
    return _diagnose(am, what, False, lambda: am.drag_with_cursor(start, end, quick=quick))


def keys_held() -> tuple:
    user32 = ctypes.windll.user32
    return tuple(vk for vk in KEYBOARD_VKS if user32.GetAsyncKeyState(vk) & 0x8000)


def release_keys(vks) -> None:
    """Solta teclas cujo soltar o BlockInput pode ter engolido.

    Se a pessoa ainda estiver segurando, a repetição do teclado aperta de novo."""
    user32 = ctypes.windll.user32
    for vk in vks:
        flags = KEYEVENTF_KEYUP
        if vk in EXTENDED_KEYS or vk in RIGHT_SIDE_MODIFIERS:
            flags |= KEYEVENTF_EXTENDEDKEY
        user32.keybd_event(vk, user32.MapVirtualKeyW(vk, 0), flags, 0)


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
        self.lock = PriorityLock()
        self.settings = dict(DEFAULT_INPUT)

    def configure(self, settings: dict) -> None:
        """Liga ao bloco "input" do perfil: mudanças na tela valem na hora."""
        self.settings = settings

    @property
    def diagnostic(self) -> bool:
        return bool(self.settings.get("diagnostic"))

    @property
    def pause(self) -> float:
        """Um quadro do cliente: menos que isso ele pode não ver um passo."""
        try:
            return min(0.2, max(0.005, float(self.settings.get("pause_ms", 30)) / 1000))
        except (TypeError, ValueError):
            return QUICK_PAUSE

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

    def client_rect_on_screen(self):
        """(left, top, width, height) da área do jogo na tela."""
        _, _, width, height = win32gui.GetClientRect(self.hwnd)
        left, top = self.client_to_screen((0, 0))
        return left, top, width, height

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
        """Reserva o mouse do jogo e segura o mouse físico; devolve se conseguiu.

        O movimento real do mouse sobre o jogo chegaria ao cliente no meio da
        sequência e faria a ação acontecer na posição errada. Só o mouse é
        segurado; se isso falhar, cai no BlockInput, que exige admin e prende
        o teclado, e por isso solta no fim as teclas que estavam apertadas.
        """
        if not self.lock.acquire(timeout=GUARD_TIMEOUT):
            yield False
            return
        blocker = MouseBlocker()
        input_blocked = False
        held = ()
        try:
            mouse_held = blocker.start()
            if not mouse_held:
                held = keys_held()
                input_blocked = set_user_input_blocked(True)
            yield mouse_held or input_blocked
        finally:
            try:
                blocker.stop()
                if input_blocked:
                    if not set_user_input_blocked(False):
                        logger.error("Falha ao liberar o input do usuário")
                    release_keys(held)
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

    def drag(self, start, end, steps: int = 12, duration: float = 0.2, quick: bool = False) -> bool:
        """Arrasta por mensagens, sem foco.

        O cliente solta o item onde está o cursor de verdade, e não onde a
        mensagem diz. Por isso o cursor fica parado em cima do destino durante o
        arrasto e só volta depois que o cliente viu o soltar."""
        sx, sy = int(start[0]), int(start[1])
        ex, ey = int(end[0]), int(end[1])
        settle, hold = (self.pause, self.pause) if quick else (0.05, 0.08)
        if quick:
            steps, duration = QUICK_STEPS, QUICK_DURATION
        pressed = False
        original = None
        try:
            with self.lock:
                original = self.get_cursor()
                self.set_cursor(self.client_to_screen((ex, ey)))
                self._send(win32con.WM_MOUSEMOVE, 0, make_lparam(sx, sy))
                time.sleep(settle)
                self._send(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, make_lparam(sx, sy))
                pressed = True
                time.sleep(hold)
                for i in range(1, steps + 1):
                    x = int(sx + (ex - sx) * i / steps)
                    y = int(sy + (ey - sy) * i / steps)
                    self._send(win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, make_lparam(x, y))
                    time.sleep(max(0.008, duration / steps))
                time.sleep(settle)
                self._send(win32con.WM_LBUTTONUP, 0, make_lparam(ex, ey))
                pressed = False
                self._send(win32con.WM_MOUSEMOVE, 0, make_lparam(ex, ey))
                time.sleep(DROP_GRACE)
            return True
        except Exception as exc:
            logger.error("Erro durante o arrasto: %s", exc)
            return False
        finally:
            if pressed:  # nunca deixa o botão "preso" no cliente
                with contextlib.suppress(Exception):
                    self._send(win32con.WM_LBUTTONUP, 0, make_lparam(ex, ey))
            if original is not None:
                with contextlib.suppress(Exception):
                    self.set_cursor(original)

    # ---------- mouse pelo cursor real (exige o jogo na frente) ----------

    @staticmethod
    def get_cursor():
        return win32api.GetCursorPos()

    @staticmethod
    def set_cursor(pos) -> None:
        ctypes.windll.user32.SetCursorPos(int(pos[0]), int(pos[1]))

    def click_with_cursor(self, pos, button: str) -> None:
        """Clique rápido no jogo, sem nunca virar arrasto.

        Só posicionar o cursor não basta: o cliente pode ler o botão ainda na
        posição anterior e, ao ver o mouse andar com ele apertado, arrastar o
        item. Por isso o movimento é de verdade e há um quadro de espera antes
        de apertar e antes de seguir."""
        mouse_event = ctypes.windll.user32.mouse_event
        down, up = MOUSE_FLAGS[button]
        with self.lock:
            self._move_cursor(*self.client_to_screen(pos))
            time.sleep(self.pause)
            mouse_event(down, 0, 0, 0, 0)
            try:
                time.sleep(self.pause)
            finally:
                mouse_event(up, 0, 0, 0, 0)
            time.sleep(self.pause)

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

        quick corta as esperas para perto do que a macro de runa usa, mas cada
        passo ainda dura o bastante para o cliente ver: rápido demais ele pega o
        item errado no caminho ou solta onde o cursor voltou."""
        step = max(self.pause, QUICK_MIN_STEP)
        settle, hold, release = (step,) * 3 if quick else (0.08, 0.10, 0.08)
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
                time.sleep(DROP_GRACE if quick else 0.10)
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
