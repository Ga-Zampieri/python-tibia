"""Leitura de pixels: battle list, assinatura dos nomes e barras de HP/mana."""
from __future__ import annotations

import time

import numpy as np

from .battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState

MAX_ROWS = 20
NAME_HEIGHT = 13
SIGNATURE_TOLERANCE = 0.12
DARK_LEVEL = 20        # moldura da barra de HP: preto puro
BAR_MIN_INNER = 2      # altura do preenchimento entre as bordas da moldura
BAR_MAX_INNER = 6
TEXT_LEVEL = 100       # texto do nome, em qualquer cor
WORD_GAP = 2           # letras da mesma palavra ficam a no máximo 2 colunas
ICON_WIDTH = 11        # caveira/escudo antes do nome: nenhuma palavra é tão estreita
PIXEL_TOLERANCE = 30
CHANGED_PIXELS_LIMIT = 0.05


def crop(frame, rect):
    """Recorta (left, top, width, height) de um frame, limitando às bordas."""
    left, top, width, height = (int(v) for v in rect)
    left, top = max(0, left), max(0, top)
    return frame[top:top + height, left:left + width]


def same_image(a, b) -> bool:
    """Compara por pixels alterados, para um item pequeno não sumir numa média."""
    if a.shape != b.shape:
        return False
    changed = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > PIXEL_TOLERANCE
    return float(changed.mean()) < CHANGED_PIXELS_LIMIT


def _bar_masks(area):
    """Cores do preenchimento da barra de HP (só usadas dentro da moldura)."""
    r = area[:, :, 0].astype(np.int16)
    g = area[:, :, 1].astype(np.int16)
    b = area[:, :, 2].astype(np.int16)
    green = (g >= 65) & (g > r * 1.20) & (g > b * 1.15) & (r < 155) & (b < 155)
    yellow = ((r >= 150) & (g >= 130) & (b < 110)
              & (r > b * 1.5) & (g > b * 1.3) & (np.abs(r - g) < 70))
    red = (r >= 70) & (r > g * 1.25) & (r > b * 1.20) & (g < 155)
    return green, yellow, red


def _longest_dark_run(row):
    """(início, fim) da maior sequência de pixels pretos da linha, ou None."""
    dark = row.max(axis=1) <= DARK_LEVEL
    if not dark.any():
        return None
    edges = np.diff(np.concatenate(([0], dark.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    best = int(np.argmax(ends - starts))
    return int(starts[best]), int(ends[best])


def _find_bars(area):
    """Barras de HP pela moldura preta: duas linhas pretas iguais com o
    preenchimento entre elas. Caveiras, sprites e o contorno de alvo nunca
    formam essa moldura, então não viram linhas fantasmas."""
    height, width = area.shape[:2]
    min_width = max(30, int(width * 0.4))
    runs = [_longest_dark_run(area[y]) for y in range(height)]
    bars = []
    y = 0
    while y < height:
        run = runs[y]
        if run is None or run[1] - run[0] + 1 < min_width:
            y += 1
            continue
        found = None
        for gap in range(BAR_MIN_INNER + 1, BAR_MAX_INNER + 2):
            other = runs[y + gap] if y + gap < height else None
            if other is None or abs(other[0] - run[0]) > 1 or abs(other[1] - run[1]) > 1:
                continue
            inner = area[y + 1:y + gap, run[0] + 1:run[1]]
            # Por dentro não pode ser tudo preto (seriam só duas bordas quaisquer).
            if inner.size and (inner.max(axis=2) > DARK_LEVEL).mean() > 0.3:
                found = gap
                break
        if found is None:
            y += 1
            continue
        bars.append((y, y + found, run[0], run[1]))
        y += found + 1
    return bars


def _hp_of(inner):
    """(estado, porcentagem) do preenchimento dentro da moldura."""
    green, yellow, red = _bar_masks(inner)
    counts = {"green": int(green.sum()), "yellow": int(yellow.sum()), "red": int(red.sum())}
    filled = (green | yellow | red).any(axis=0)
    percent = round(float(filled.sum()) * 100.0 / max(1, inner.shape[1]), 1)
    if not any(counts.values()):
        return "red", 0.0
    return max(counts, key=counts.get), percent


def _is_row_selected(area, row_top, row_bottom, bar_top, bar_bottom) -> bool:
    """Contorno vermelho acima/abaixo da barra, para não confundir com HP baixo."""
    red = total = 0
    for y0, y1 in ((row_top, bar_top), (bar_bottom + 1, row_bottom)):
        strip = area[max(0, y0):max(0, y1)]
        if strip.size == 0:
            continue
        r = strip[:, :, 0].astype(np.int16)
        g = strip[:, :, 1].astype(np.int16)
        b = strip[:, :, 2].astype(np.int16)
        # Contorno e nome do alvo: vermelho puro, ou rosa (255,136,136) com o mouse
        # em cima. Caveira vermelha é mais escura; o hover sozinho é branco.
        target = (r >= 200) & (g <= 60) & (b <= 60)
        hovered_target = (r >= 230) & (g >= 100) & (g <= 170) & (np.abs(g - b) <= 15)
        red += int((target | hovered_target).sum())
        total += strip.shape[0] * strip.shape[1]
    return total > 0 and red / total > 0.015


def _drop_leading_icons(ink):
    """Tira caveira/escudo da frente do nome. Junta as letras em palavras (as
    letras ficam a 1 coluna uma da outra) e descarta a primeira "palavra" se ela
    for estreita como um ícone e vier separada do resto por um espaço."""
    columns = ink.any(axis=0)
    xs = np.flatnonzero(columns)
    if len(xs) == 0:
        return ink
    words = [[int(xs[0]), int(xs[0])]]
    for x in xs[1:]:
        if x - words[-1][1] <= WORD_GAP:
            words[-1][1] = int(x)
        else:
            words.append([int(x), int(x)])
    while len(words) > 1 and words[0][1] - words[0][0] + 1 <= ICON_WIDTH:
        ink[:, :words[1][0]] = False
        words.pop(0)
    return ink


def name_signature(pixels) -> str:
    """Forma do texto do nome. A fonte do cliente é fixa, então o mesmo nome gera
    sempre o mesmo desenho, em qualquer cor: cinza, branco com o mouse em cima,
    vermelho quando é o alvo. Ícones na frente do nome são descartados."""
    if pixels.size == 0:
        return ""
    ink = _drop_leading_icons(pixels.max(axis=2) >= TEXT_LEVEL)
    ys, xs = np.nonzero(ink)
    if len(xs) < 4:
        return ""
    ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    height, width = ink.shape
    return f"{width}x{height}:{np.packbits(ink).tobytes().hex()}"


def _unpack_signature(signature: str):
    size, _, data = signature.partition(":")
    width, height = (int(v) for v in size.split("x"))
    bits = np.unpackbits(np.frombuffer(bytes.fromhex(data), dtype=np.uint8))
    return bits[:width * height].reshape(height, width).astype(bool)


def signature_image(signature: str, padding: int = 2):
    """Desenha o nome salvo (texto claro em fundo escuro), para mostrar na tela."""
    try:
        ink = _unpack_signature(signature)
    except ValueError:
        return None
    height, width = ink.shape
    image = np.full((height + 2 * padding, width + 2 * padding, 3), 30, dtype=np.uint8)
    image[padding:padding + height, padding:padding + width][ink] = 220
    return image


def signatures_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        left, right = _unpack_signature(a), _unpack_signature(b)
    except ValueError:
        return False
    if abs(left.shape[0] - right.shape[0]) > 1 or abs(left.shape[1] - right.shape[1]) > 2:
        return False
    height = min(left.shape[0], right.shape[0])
    width = min(left.shape[1], right.shape[1])
    differing = np.count_nonzero(left[:height, :width] != right[:height, :width])
    return differing / max(1, np.count_nonzero(left)) <= SIGNATURE_TOLERANCE


def analyze_battle_list(frame, region, allowed=(), ignored=()):
    """Monta o snapshot da battle list. `region` e os bounds são coordenadas cliente.

    `allowed`: nomes para atacar (vazia = qualquer um). `ignored`: nomes que
    nunca são atacados, mas também não contam como desconhecidos no Alarme."""
    now = time.time()
    empty = BattleListSnapshot((), SelectorState.UNCERTAIN, False, now, None)
    if frame is None or region is None:
        return empty
    left, top = int(region[0]), int(region[1])
    area = crop(frame, region)
    height, width = area.shape[:2]
    if height < 5 or width < 10:
        return empty

    rows = []
    selected = None
    for bar_top, bar_bottom, bar_left, bar_right in _find_bars(area):
        row_top = max(0, bar_top - NAME_HEIGHT)
        row_bottom = min(height, bar_bottom + 3)
        hp_state, hp_percent = _hp_of(area[bar_top + 1:bar_bottom, bar_left + 1:bar_right])
        signature = name_signature(area[row_top:bar_top, bar_left:bar_right + 1])
        is_ignored = any(signatures_match(signature, known) for known in ignored)
        is_allowed = not is_ignored and (
            not allowed or any(signatures_match(signature, known) for known in allowed))

        index = len(rows)
        rows.append(BattleListRow(
            index=index,
            bounds=(left, top + row_top, left + width, top + row_bottom),
            confidence=0.98,
            hp_state=hp_state,
            signature=signature,
            allowed=is_allowed,
            ignored=is_ignored,
            hp_percent=hp_percent,
        ))
        if _is_row_selected(area, row_top, row_bottom, bar_top, bar_bottom):
            selected = index
        if len(rows) >= MAX_ROWS:
            break

    if not rows:
        return empty
    return BattleListSnapshot(tuple(rows), SelectorState.VALID, True, now, selected)


def bar_percent(frame, rect):
    """Quanto da barra horizontal está preenchido (0-100), ou None sem imagem.

    A parte vazia é escura ou cinza; a preenchida é colorida, em qualquer cor.
    """
    if frame is None or rect is None:
        return None
    area = crop(frame, rect)
    if area.size == 0:
        return None
    high = area.max(axis=2).astype(np.int16)
    low = area.min(axis=2).astype(np.int16)
    filled = ((high - low) > 40) & (high > 70)
    hits = np.flatnonzero(filled.mean(axis=0) >= 0.5)
    if len(hits) == 0:
        return 0.0
    return round((int(hits[-1]) + 1) * 100.0 / area.shape[1], 1)
