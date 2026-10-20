from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterable, List, Tuple


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUT(ctypes.Structure):
    class _union(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    _anonymous_ = ("_union",)
    _fields_ = [("type", wintypes.DWORD), ("_union", _union)]


class WindowsSendInputController:
    """Nativo Win32 da API SendInput, adaptado para automação do mouse e teclado."""

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    KEYEVENTF_KEYUP = 0x0002

    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32
        self.position = (0, 0)
        self.pending: List[Tuple[str, tuple]] = []
        self.cancel_requested = False

    def _to_absolute_position(self, x: int, y: int) -> Tuple[int, int]:
        return (int(x), int(y))

    def move_to(self, x: int, y: int) -> bool:
        self.position = self._to_absolute_position(x, y)
        return True

    def move_relative(self, dx: int, dy: int) -> bool:
        x, y = self.position
        self.position = (x + int(dx), y + int(dy))
        return True

    def click_left(self) -> bool:
        return self._mouse_click(self.MOUSEEVENTF_LEFTDOWN, self.MOUSEEVENTF_LEFTUP)

    def click_right(self) -> bool:
        return self._mouse_click(self.MOUSEEVENTF_RIGHTDOWN, self.MOUSEEVENTF_RIGHTUP)

    def _mouse_click(self, down_flag: int, up_flag: int) -> bool:
        inputs = (INPUT * 2)()
        inputs[0].type = 0
        inputs[0]._union.mi = MOUSEINPUT(0, 0, 0, down_flag, 0, 0)
        inputs[1].type = 0
        inputs[1]._union.mi = MOUSEINPUT(0, 0, 0, up_flag, 0, 0)
        return self.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT)) == 2

    def mouse_down(self, button: str) -> bool:
        flag = self.MOUSEEVENTF_LEFTDOWN if button.lower() == "left" else self.MOUSEEVENTF_RIGHTDOWN
        return self._send_mouse(flag)

    def mouse_up(self, button: str) -> bool:
        flag = self.MOUSEEVENTF_LEFTUP if button.lower() == "left" else self.MOUSEEVENTF_RIGHTUP
        return self._send_mouse(flag)

    def _send_mouse(self, flag: int) -> bool:
        inputs = (INPUT * 1)()
        inputs[0].type = 0
        inputs[0]._union.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
        return self.user32.SendInput(1, ctypes.byref(inputs), ctypes.sizeof(INPUT)) == 1

    def press_key(self, key: str) -> bool:
        vk = self._key_to_vk(key)
        if vk is None:
            return False
        inputs = (INPUT * 1)()
        inputs[0].type = 1
        inputs[0]._union.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
        return self.user32.SendInput(1, ctypes.byref(inputs), ctypes.sizeof(INPUT)) == 1

    def release_key(self, key: str) -> bool:
        vk = self._key_to_vk(key)
        if vk is None:
            return False
        inputs = (INPUT * 1)()
        inputs[0].type = 1
        inputs[0]._union.ki = KEYBDINPUT(vk, 0, self.KEYEVENTF_KEYUP, 0, 0)
        return self.user32.SendInput(1, ctypes.byref(inputs), ctypes.sizeof(INPUT)) == 1

    def _key_to_vk(self, key: str) -> int | None:
        mapping = {
            "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
            "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
            "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
            "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
            "y": 0x59, "z": 0x5A, "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33,
            "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
            "esc": 0x1B, "enter": 0x0D, "space": 0x20,
        }
        return mapping.get(str(key).lower())

    def execute_batch(self, actions: Iterable[Tuple[str, tuple]]) -> bool:
        self.pending.extend(list(actions))
        for action_name, args in self.pending:
            if self.cancel_requested:
                break
            method = getattr(self, action_name, None)
            if method is not None:
                method(*args)
        self.pending.clear()
        return True

    def cancel_pending_actions(self) -> None:
        self.cancel_requested = True
        self.pending.clear()
