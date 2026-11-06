"""Captura da área cliente do jogo.

Tenta PrintWindow, que funciona com o jogo coberto por outra janela. Quando o
cliente não responde (imagem uniforme), lê a tela, e aí o jogo precisa estar visível.
"""
from __future__ import annotations

import ctypes
import logging
import threading

import numpy as np
import win32gui
import win32ui

try:
    import mss
except Exception:  # pragma: no cover
    mss = None

logger = logging.getLogger(__name__)

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2

_local = threading.local()


def virtual_screen_bounds():
    """(left, top, width, height) cobrindo todos os monitores."""
    metric = ctypes.windll.user32.GetSystemMetrics
    return metric(76), metric(77), metric(78), metric(79)


def _print_window(hwnd: int):
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        return None
    window_dc = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(window_dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        if not ctypes.windll.user32.PrintWindow(
            hwnd, memory.GetSafeHdc(), PW_CLIENTONLY | PW_RENDERFULLCONTENT
        ):
            return None
        bgra = np.frombuffer(bitmap.GetBitmapBits(True), dtype=np.uint8)
        return bgra.reshape(height, width, 4)[:, :, 2::-1].copy()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)


def _grab_from_screen(hwnd: int):
    if mss is None:
        return None
    _, _, width, height = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    if not hasattr(_local, "mss"):
        _local.mss = mss.mss()  # a instância do mss não é compartilhável entre threads
    shot = _local.mss.grab({"left": left, "top": top, "width": width, "height": height})
    return np.asarray(shot)[:, :, 2::-1].copy()


def _is_blank(frame) -> bool:
    return frame is None or frame.size == 0 or int(frame.max()) == int(frame.min())


def capture_client(hwnd: int):
    """Frame RGB da área cliente, ou None se não houver imagem (ex.: minimizado)."""
    try:
        if win32gui.IsIconic(hwnd):
            return None
        frame = _print_window(hwnd)
        if not _is_blank(frame):
            return frame
    except Exception as exc:
        logger.debug("PrintWindow falhou: %s", exc)
    try:
        return _grab_from_screen(hwnd)
    except Exception as exc:
        logger.warning("Falha ao capturar a tela: %s", exc)
        return None
