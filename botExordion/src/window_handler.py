import logging
import re

import pygetwindow as gw

logger = logging.getLogger(__name__)

GAME_TITLE = re.compile(r"tibia|otclient|otserv|\bot\b", re.IGNORECASE)
NOT_GAME = re.compile(
    r"exordion|visual studio|chrome|firefox|edge|opera|brave|explorer|notepad|discord|youtube",
    re.IGNORECASE,
)


def getWindows():
    """Janelas visíveis com título, como (título, hwnd), em ordem alfabética."""
    result = []
    for win in gw.getAllWindows():
        title = getattr(win, "title", "") or ""
        hwnd = getattr(win, "_hWnd", None)
        if title.strip() and hwnd is not None:
            result.append((title, int(hwnd)))
    return sorted(result, key=lambda item: item[0].lower())


def pick_game_window(windows, saved_title: str = ""):
    """hwnd do jogo: o título salvo vence; senão, só se houver um candidato claro."""
    if saved_title:
        for title, hwnd in windows:
            if title == saved_title:
                return hwnd
    candidates = [
        hwnd for title, hwnd in windows
        if GAME_TITLE.search(title) and not NOT_GAME.search(title)
    ]
    return candidates[0] if len(candidates) == 1 else None
