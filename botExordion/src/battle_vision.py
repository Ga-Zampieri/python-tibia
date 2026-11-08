"""Leitura de pixels: battle list, assinatura dos nomes e barras de HP/mana."""
from __future__ import annotations

import time

import numpy as np

from .battle_list_selector import BattleListRow, BattleListSnapshot, SelectorState

MAX_ROWS = 20
NAME_HEIGHT = 13
SIGNATURE_TOLERANCE = 0.12
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
    r = area[:, :, 0].astype(np.int16)
    g = area[:, :, 1].astype(np.int16)
    b = area[:, :, 2].astype(np.int16)
    green = (g >= 65) & (g > r * 1.20) & (g > b * 1.15) & (r < 155) & (b < 155)
    yellow = ((r >= 150) & (g >= 130) & (b < 110)
              & (r > b * 1.5) & (g > b * 1.3) & (np.abs(r - g) < 70))
    red = (r >= 100) & (r > g * 1.25) & (r > b * 1.20) & (g < 155)
    return green, yellow, red


def _group_rows(mask, width):
    min_pixels = max(8, int(width * 0.04))
    min_span = max(12, int(width * 0.06))
    active = []
    for y in range(mask.shape[0]):
        xs = np.flatnonzero(mask[y])
        if len(xs) >= min_pixels and int(xs[-1]) - int(xs[0]) + 1 >= min_span:
            active.append(y)
    if not active:
        return []
    blocks = []
    top = bottom = active[0]
    for y in active[1:]:
        if y - bottom <= 4:
            bottom = y
        else:
            blocks.append((top, bottom))
            top = bottom = y
    blocks.append((top, bottom))
    return [block for block in blocks if block[1] > block[0]]


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
        red += int(((r > 160) & (g < 120) & (b < 120)).sum())
        total += strip.shape[0] * strip.shape[1]
    return total > 0 and red / total > 0.03


def name_signature(pixels) -> str:
    """Forma do texto do nome. A fonte do cliente é fixa, então o mesmo nome gera
    sempre o mesmo desenho, seja qual for a cor."""
    if pixels.size == 0:
        return ""
    ink = pixels.max(axis=2) >= 130
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


def analyze_battle_list(frame, region, allowed=()):
    """Monta o snapshot da battle list. `region` e os bounds são coordenadas cliente."""
    now = time.time()
    empty = BattleListSnapshot((), SelectorState.UNCERTAIN, False, now, None)
    if frame is None or region is None:
        return empty
    left, top = int(region[0]), int(region[1])
    area_full = crop(frame, region)
    height, width = area_full.shape[:2]
    if height < 5 or width < 10:
        return empty

    start_y = min(25, height // 4)  # pula o título da janela da battle list
    area = area_full[start_y:]
    green, yellow, red = _bar_masks(area)
    mask = green | yellow | red

    rows = []
    selected = None
    last_center = None
    for bar_top, bar_bottom in _group_rows(mask, width):
        row_top = max(0, bar_top - NAME_HEIGHT)
        row_bottom = min(area.shape[0], bar_bottom + 4)
        center = (row_top + row_bottom) // 2
        if last_center is not None and abs(center - last_center) <= 4:
            continue
        last_center = center

        band = slice(bar_top, bar_bottom + 1)
        counts = {
            "green": int(green[band].sum()),
            "yellow": int(yellow[band].sum()),
            "red": int(red[band].sum()),
        }
        hp_state = max(counts, key=counts.get)

        bar_left = int(np.flatnonzero(mask[band].any(axis=0))[0])
        signature = name_signature(area[row_top:bar_top, bar_left:])
        is_allowed = not allowed or any(signatures_match(signature, known) for known in allowed)

        index = len(rows)
        rows.append(BattleListRow(
            index=index,
            bounds=(left, top + start_y + row_top, left + width, top + start_y + row_bottom),
            confidence=0.98,
            hp_state=hp_state,
            signature=signature,
            allowed=is_allowed,
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
