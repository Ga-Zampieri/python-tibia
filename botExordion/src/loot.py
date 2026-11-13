"""Loot por imagem: pega de um container aberto os itens que o usuário ensinou.

O cliente desenha os itens sem escala, então o mesmo item é sempre o mesmo desenho.
A quantidade da pilha fica no canto do slot, que a comparação ignora.
"""
from __future__ import annotations

import base64
import binascii
import functools
import logging
import threading
import zlib
from collections import namedtuple

import numpy as np

import time

from .action_manager import click_item, drag_item, priority
from .battle_vision import crop

logger = logging.getLogger(__name__)

SLOT = 32
PITCH = 37  # slot + moldura + vão
GRID_MARGIN = 8  # a seleção é feita à mão e pode cortar a borda do slot
EMPTY_RANGE = 60  # o fundo do slot vazio é uma textura escura e quase sem contraste
PIXEL_TOLERANCE = 30
CHANGED_PIXELS_LIMIT = 0.02
MAX_STEPS = 40
CHANGE_CHECK_SECONDS = 0.05
SCROLL_SECONDS = 0.6  # a rolagem é local e não espera o servidor
VIEW_ABOVE = 5  # a área rolável começa acima do primeiro slot
VIEW_BELOW = 1  # e termina na moldura da janela, antes do fim do último vão
MIN_VISIBLE = 24  # cada clique rola 14 px, então a fileira costuma aparecer cortada
EDGE_CONTRAST = 6
SCROLL_X = 6  # do fim da grade até o centro da barra de rolagem
SCROLL_UP_Y = 1
SCROLL_DOWN_Y = 8

LIST_FORMAT = "exordion-loot"
SPRITE_BYTES = SLOT * SLOT * 3

COMPARED = np.ones((SLOT, SLOT), dtype=bool)
COMPARED[18:, 8:] = False  # números da pilha

# pixels pode ser só a parte visível; skip diz quantas linhas de cima a rolagem cortou.
Slot = namedtuple("Slot", "left top pixels skip", defaults=(0,))


def _slot_score(brightness, x: int, y: int) -> float:
    """Marca da moldura: escura em cima e à esquerda, clara embaixo e à direita.

    O lado claro é contínuo, e por isso vale o pior pixel: o desenho de um item
    pode imitar a média de uma borda, mas não uma linha inteira."""
    end_x, end_y = x + SLOT, y + SLOT
    return min(
        (brightness[y, x:end_x] - brightness[y - 1, x:end_x]).mean(),
        (brightness[y:end_y, x] - brightness[y:end_y, x - 1]).mean(),
        (brightness[end_y, x:end_x] - brightness[end_y + 1, x:end_x]).min(),
        (brightness[y:end_y, end_x] - brightness[y:end_y, end_x + 1]).min(),
    )


def find_grid(frame, rect):
    """Encaixa uma seleção aproximada na grade. Devolve [left, top, colunas, linhas]."""
    left = max(0, int(rect[0]) - GRID_MARGIN)
    top = max(0, int(rect[1]) - GRID_MARGIN)
    right = int(rect[0]) + int(rect[2]) + GRID_MARGIN
    bottom = int(rect[1]) + int(rect[3]) + GRID_MARGIN
    area = crop(frame, (left, top, right - left, bottom - top)).astype(np.float32).mean(axis=2)
    height, width = area.shape
    scores = {(x, y): _slot_score(area, x, y)
              for y in range(1, height - SLOT - 1) for x in range(1, width - SLOT - 1)}
    if not scores:
        return None
    best_x, best_y = max(scores, key=scores.get)
    limit = scores[best_x, best_y] / 2
    if limit <= 0:
        return None
    found = [(x, y) for (x, y), score in scores.items() if score >= limit
             and (x - best_x) % PITCH == 0 and (y - best_y) % PITCH == 0]
    xs, ys = [x for x, _ in found], [y for _, y in found]
    return [left + min(xs), top + min(ys),
            (max(xs) - min(xs)) // PITCH + 1, (max(ys) - min(ys)) // PITCH + 1]


def view_bounds(grid):
    top, rows = grid[1], grid[3]
    return top - VIEW_ABOVE, top + rows * PITCH - VIEW_BELOW


def row_shift(frame, grid):
    """Quantos pixels a rolagem deslocou as fileiras, de 0 a PITCH - 1, ou None sem slots.

    Usa a borda clara: a área é mais alta que uma fileira, então sempre aparece uma."""
    left, top = grid[:2]
    start, end = view_bounds(grid)
    area = crop(frame, (left, start, SLOT, end - start + 1)).astype(np.float32).mean(axis=2)
    if area.shape[1] < SLOT:
        return None
    for y in range(area.shape[0] - 1):
        if (area[y] - area[y + 1]).min() > EDGE_CONTRAST:
            return (top + SLOT - (start + y)) % PITCH
    return None


def window_open(frame, grid, scrolled: bool = False) -> bool:
    """Confere se há um container nos slots, para o X nunca cair em outra janela."""
    shift = row_shift(frame, grid)
    return shift is not None if scrolled else shift == 0


def read_slots(frame, grid) -> list:
    left, top, columns, rows = grid
    slots = []
    for row in range(rows):
        for column in range(columns):
            x, y = left + column * PITCH, top + row * PITCH
            pixels = crop(frame, (x, y, SLOT, SLOT))
            if pixels.shape[:2] == (SLOT, SLOT):
                slots.append(Slot(x, y, pixels))
    return slots


def read_view(frame, grid) -> list:
    """Lê as fileiras que a rolagem deixou visíveis, mesmo cortadas."""
    left, top, columns, _ = grid
    shift = row_shift(frame, grid)
    if not shift:
        return read_slots(frame, grid)
    start, end = view_bounds(grid)
    slots = []
    for row_top in range(top - shift, end, PITCH):
        first, last = max(row_top, start), min(row_top + SLOT, end)
        if last - first < MIN_VISIBLE:
            continue
        for column in range(columns):
            x = left + column * PITCH
            slots.append(Slot(x, first, crop(frame, (x, first, SLOT, last - first)), first - row_top))
    return slots


def capture_area(grid):
    """Retângulo (cliente) com tudo o que o loot olha: slots, rolagem e moldura."""
    if not grid:
        return None
    left, _, columns, _ = grid
    start, end = view_bounds(grid)
    return (left - 2, start - 2, columns * PITCH + SCROLL_X + 12, end - start + 4)


def scroll_point(grid, down: bool):
    left, top, columns, rows = grid
    y = top + rows * PITCH - SCROLL_DOWN_Y if down else top + SCROLL_UP_Y
    return left + columns * PITCH + SCROLL_X, y


def is_empty(pixels) -> bool:
    return int(pixels.max()) - int(pixels.min()) < EMPTY_RANGE


def changed_pixels(a, b):
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > PIXEL_TOLERANCE


def same_item(a, b, skip: int = 0) -> bool:
    """a pode ser só a parte visível de b, a partir da linha skip."""
    lines = slice(skip, skip + a.shape[0])
    return float(changed_pixels(a, b[lines])[COMPARED[lines]].mean()) < CHANGED_PIXELS_LIMIT


def encode_sprite(pixels) -> str:
    return base64.b64encode(zlib.compress(np.ascontiguousarray(pixels).tobytes())).decode("ascii")


@functools.lru_cache(maxsize=512)
def decode_sprite(data: str):
    # O limite importa porque a lista pode vir de um arquivo de outra pessoa.
    raw = zlib.decompressobj().decompress(base64.b64decode(data), SPRITE_BYTES + 1)
    return np.frombuffer(raw, dtype=np.uint8).reshape(SLOT, SLOT, 3)


def match(pixels, sprites, skip: int = 0):
    return next((sprite for sprite in sprites if same_item(pixels, decode_sprite(sprite), skip)), None)


def is_known(pixels, sprites, skip: int = 0) -> bool:
    return match(pixels, sprites, skip) is not None


def destinations(config: dict) -> list:
    return [config["destination"], *config["extra_destinations"]]


def destination_of(config: dict, sprite: str) -> int:
    """Índice da BP do item. Uma lista importada pode citar BP que aqui não existe."""
    index = config["routes"].get(sprite, 0)
    return index if index < len(destinations(config)) else 0


def set_route(config: dict, sprite: str, index: int) -> None:
    if index:
        config["routes"][sprite] = index
    else:
        config["routes"].pop(sprite, None)


def remove_destination(config: dict, index: int) -> None:
    """Tira uma BP extra. Os itens dela voltam para a BP 1 e as seguintes sobem um número."""
    del config["extra_destinations"][index - 1]
    routes = {sprite: route - (route > index) for sprite, route in config["routes"].items() if route != index}
    config["routes"] = routes


def export_list(config: dict) -> dict:
    """Desenhos e o número da BP de cada um: slots, destinos e X dependem da tela de cada pessoa."""
    return {"format": LIST_FORMAT, "version": 1, "items": config["items"], "bags": config["bags"],
            "routes": config["routes"]}


def _valid_sprite(sprite) -> bool:
    try:
        decode_sprite(sprite)
        return True
    except (TypeError, ValueError, binascii.Error, zlib.error):
        return False


def import_list(config: dict, data) -> int | None:
    """Soma a lista à atual sem repetir. Devolve quantos entraram, ou None se não for uma lista."""
    if not isinstance(data, dict) or data.get("format") != LIST_FORMAT:
        return None
    lists = {kind: data.get(kind, []) for kind in ("items", "bags")}
    if not all(isinstance(sprites, list) and all(map(_valid_sprite, sprites)) for sprites in lists.values()):
        return None
    routes = data.get("routes", {})
    if not isinstance(routes, dict) or not all(type(route) is int and route >= 0 for route in routes.values()):
        return None
    added = 0
    for kind, sprites in lists.items():
        for sprite in sprites:
            if not is_known(decode_sprite(sprite), config["items"] + config["bags"]):
                config[kind].append(sprite)
                set_route(config, sprite, routes.get(sprite, 0))
                added += 1
    return added


def view_changed(before, after) -> bool:
    # Compara tudo: se saiu um de dois itens iguais, o slot dele continua igual.
    if len(before) != len(after):
        return True
    return any(a.pixels.shape != b.pixels.shape or not same_item(a.pixels, b.pixels)
               for a, b in zip(before, after))


class Looter:
    def __init__(self, profile: dict, log=logger.info, get_frame=lambda: None, alert=None):
        self.am = None
        self.profile = profile
        self.config = profile["loot"]
        self.log = log
        self.get_frame = get_frame
        self.alert = alert or log
        self.taken = 0
        self._finished = False
        self._loot_left_behind = False
        self._scrolled = 0
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def missing(self) -> str:
        if not self.config["grid"]:
            return "os slots do loot"
        if not self.config["destination"]:
            return "o destino"
        if not self.config["items"] and not self.config["bags"]:
            return "os itens"
        return ""

    def start(self) -> bool:
        if self.is_running or self.am is None or self.missing():
            return False
        self.taken = 0
        self._finished = False
        self._loot_left_behind = False
        self._scrolled = 0
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="loot")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    def classify(self, pixels, skip: int = 0):
        """"item", "bag", "other" ou None para slot vazio."""
        if is_empty(pixels):
            return None
        if is_known(pixels, self.config["items"], skip):
            return "item"
        if is_known(pixels, self.config["bags"], skip):
            return "bag"
        return "other"

    def _read(self):
        frame = self.get_frame()
        return None if frame is None else read_view(frame, self.config["grid"])

    def _kinds(self, view) -> list:
        return [self.classify(slot.pixels, slot.skip) for slot in view]

    def _first(self, view, kind):
        return next((slot for slot in view if self.classify(slot.pixels, slot.skip) == kind), None)

    def _server_wait(self) -> float:
        """Quanto esperar o servidor responder (Ajustes > Input). Por tempo, e não por
        contagem: com a captura rápida, cada olhada leva bem menos."""
        try:
            return max(0.0, float(self.profile["input"]["server_wait"]))
        except (TypeError, ValueError):
            return 2.0

    def _checks(self, seconds: float):
        deadline = time.monotonic() + seconds
        while True:
            yield
            if time.monotonic() >= deadline:
                return

    def _wait_change(self, before):
        """True se mudou, False se não mudou e None se pararam ou a imagem sumiu."""
        for _ in self._checks(self._server_wait()):
            if self._stop_event.wait(CHANGE_CHECK_SECONDS):
                return None
            after = self._read()
            if after is None:
                return None
            if view_changed(before, after):
                return True
        return False

    def _give_up(self, message: str) -> bool:
        self._stop_event.set()
        self.alert(message)
        return False

    def _act(self, action) -> bool:
        with self.am.guarded() as blocked:
            if not blocked:
                self._stop_event.set()
                self.log("Loot: não foi possível segurar o mouse.")
                return False
            return bool(action())

    def _click(self, pos, button: str) -> bool:
        return self._act(lambda: click_item(self.am, pos, button, background=True, interface=True))

    def _take(self, slot, view) -> bool:
        start = self._center(slot)
        sprite = match(slot.pixels, self.config["items"], slot.skip)
        end = destinations(self.config)[destination_of(self.config, sprite)]
        background = self.profile["drag_in_background"]
        moved = self._act(lambda: drag_item(self.am, start, end, background, quick=True))
        changed = self._wait_change(view) if moved else None
        if changed is False:
            # Uma tentativa só: o corpo fica para trás, aberto, e o próximo aperto começa do zero.
            return self._give_up("Loot: um item não saiu do lugar e deixei esse corpo. Sem cap ou mochila cheia?")
        if changed:
            self.taken += 1
        return bool(changed)

    def _open(self, slot, view) -> bool:
        if not self._click(self._center(slot), "right"):
            return False
        changed = self._wait_change(view)
        if changed is False:
            return self._give_up("Loot parou: a bag não abriu na mesma janela.")
        if changed:
            self._back_to_top()
        return bool(changed)

    @staticmethod
    def _center(slot):
        return slot.left + SLOT // 2, slot.top + slot.pixels.shape[0] // 2

    def _scroll_area(self):
        frame = self.get_frame()
        if frame is None:
            return None
        left, _, columns, _ = self.config["grid"]
        start, end = view_bounds(self.config["grid"])
        return crop(frame, (left, start, columns * PITCH, end - start))

    def _scroll(self, down: bool = True) -> bool:
        """True se a lista andou; False quer dizer que ela já estava no fim."""
        before = self._scroll_area()
        if before is None or not self._click(scroll_point(self.config["grid"], down), "left"):
            return False
        for _ in self._checks(min(SCROLL_SECONDS, self._server_wait())):
            if self._stop_event.wait(CHANGE_CHECK_SECONDS):
                return False
            after = self._scroll_area()
            if after is None:
                return False
            if float(changed_pixels(before, after).mean()) > CHANGED_PIXELS_LIMIT:
                return True
        return False

    def _back_to_top(self) -> None:
        # A bag abre na mesma janela, e a rolagem do corpo pode esconder o começo dela.
        for _ in range(self._scrolled):
            if not self._scroll(down=False):
                break
        self._scrolled = 0

    def _step(self) -> bool:
        view = self._read()
        if view is None:
            self.log("Loot: sem imagem do jogo.")
            return False
        item = self._first(view, "item")
        if item is not None:
            return self._take(item, view)
        bag = self._first(view, "bag")
        if bag is not None:
            # A bag abre no lugar do corpo, que só volta pela seta da janela.
            kinds = self._kinds(view)
            if kinds.count("bag") > 1 or None not in kinds:
                self._loot_left_behind = True
            return self._open(bag, view)
        # Os slots enchem em ordem: depois de um vazio não tem mais nada.
        if None not in self._kinds(view) and self._scroll():
            self._scrolled += 1
            return True
        self._finished = True
        return False

    def _close(self) -> None:
        point = self.config["close"]
        if self._loot_left_behind:
            self.log("Loot: pode ter ficado loot no corpo. Volte pela seta e aperte de novo.")
        elif point:
            if not self._window_open():
                self.log("Loot: não vi a janela nos slots, então não cliquei no X.")
            elif self._click(point, "left") and not self._closed():
                self.log("Loot: cliquei no X, mas a janela continuou aberta.")

    def _window_open(self) -> bool:
        frame = self.get_frame()
        return frame is not None and window_open(frame, self.config["grid"], self._scrolled > 0)

    def _closed(self) -> bool:
        for _ in self._checks(min(SCROLL_SECONDS, self._server_wait())):
            if self._stop_event.wait(CHANGE_CHECK_SECONDS) or not self._window_open():
                return True
        return False

    def _run(self) -> None:
        try:
            with priority("loot"):
                for _ in range(MAX_STEPS):
                    if self._stop_event.is_set() or not self._step():
                        break
                if self._finished and not self._stop_event.is_set():
                    self._close()
            self.log(f"Loot: {self.taken} item(ns) pego(s).")
        except Exception:
            logger.exception("Erro no loot")
        finally:
            self._stop_event.set()
