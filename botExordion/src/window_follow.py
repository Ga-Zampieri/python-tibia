"""Mantém a janela do bot junto da janela do jogo."""
from __future__ import annotations

import win32con
import win32gui

QUIET = win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE


def follow_step(game, last_game, bot, offset):
    """Decide para onde vai o bot. Devolve (posição nova ou None, distância até o jogo).

    `game` e `last_game` são o canto do jogo agora e na última olhada (None se ele
    acabou de aparecer); `bot` é o canto do bot; `offset`, a distância salva.
    Se o jogo andou, ou acabou de aparecer, o bot vai junto. Se só o bot andou,
    foi a pessoa que o arrastou, e a distância nova passa a valer."""
    game = tuple(game)
    if offset is not None and (last_game is None or game != tuple(last_game)):
        target = (game[0] + offset[0], game[1] + offset[1])
        return (target if target != tuple(bot) else None), list(offset)
    return None, [bot[0] - game[0], bot[1] - game[1]]


def window_origin(hwnd):
    left, top, _, _ = win32gui.GetWindowRect(hwnd)
    return left, top


def move_window(hwnd, x, y) -> None:
    win32gui.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0, QUIET | win32con.SWP_NOZORDER)


def raise_without_focus(hwnd) -> None:
    """Põe o bot acima de tudo e tira o "sempre no topo" logo em seguida: ele fica
    na frente do jogo, e o jogo continua com o foco."""
    for place in (win32con.HWND_TOPMOST, win32con.HWND_NOTOPMOST):
        win32gui.SetWindowPos(hwnd, place, 0, 0, 0, 0, QUIET | win32con.SWP_NOMOVE)
