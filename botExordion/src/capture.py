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
        _local.mss = (getattr(mss, "MSS", None) or mss.mss)()  # não é compartilhável entre threads
    shot = _local.mss.grab({"left": left, "top": top, "width": width, "height": height})
    return np.asarray(shot)[:, :, 2::-1].copy()


def _intersects(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _visible(hwnd: int, rect) -> bool:
    """Cantos e centro do retângulo (tela) caem na janela do jogo, e não em outra."""
    left, top, width, height = rect
    points = [(left, top), (left + width - 1, top), (left, top + height - 1),
              (left + width - 1, top + height - 1), (left + width // 2, top + height // 2)]
    return all(ctypes.windll.user32.GetAncestor(win32gui.WindowFromPoint(point), 2) == hwnd
               for point in points)


def grab_visible_areas(hwnd: int, areas, covering=()):
    """Frame do tamanho da área cliente com só esses retângulos lidos da tela.

    Ler a tela custa um quadro (uns 17 ms) qualquer que seja o tamanho, contra uns
    50 ms do PrintWindow do jogo inteiro; por isso é uma leitura só, do retângulo
    que cobre todas as áreas. Só vale com o jogo na frente e nada por cima; senão
    devolve None e quem chamou usa a captura completa. `covering` são janelas do
    próprio bot, que o mouse atravessa e por isso o WindowFromPoint não enxerga."""
    try:
        if mss is None or win32gui.GetForegroundWindow() != hwnd or win32gui.IsIconic(hwnd):
            return None
        _, _, client_width, client_height = win32gui.GetClientRect(hwnd)
        origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
        boxes = []
        for area in areas:
            left, top = max(0, int(area[0])), max(0, int(area[1]))
            right = min(client_width, int(area[0]) + int(area[2]))
            bottom = min(client_height, int(area[1]) + int(area[3]))
            if right <= left or bottom <= top:
                continue
            screen = (origin_x + left, origin_y + top, right - left, bottom - top)
            if any(_intersects(screen, other) for other in covering) or not _visible(hwnd, screen):
                return None
            boxes.append((left, top, right, bottom))
        if not boxes:
            return None
        left, top = min(box[0] for box in boxes), min(box[1] for box in boxes)
        right, bottom = max(box[2] for box in boxes), max(box[3] for box in boxes)
        if not hasattr(_local, "mss"):
            _local.mss = (getattr(mss, "MSS", None) or mss.mss)()
        shot = _local.mss.grab({"left": origin_x + left, "top": origin_y + top,
                                "width": right - left, "height": bottom - top})
        frame = np.zeros((client_height, client_width, 3), dtype=np.uint8)  # zeros não custa até ser escrito
        frame[top:bottom, left:right] = np.asarray(shot)[:, :, 2::-1]
        return frame
    except Exception as exc:
        logger.debug("Captura rápida indisponível: %s", exc)
        return None


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
