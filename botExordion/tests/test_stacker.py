from pathlib import Path

import numpy as np
from PIL import Image

from conftest import FakeActionManager
from src import loot, stacker
from src.settings import DEFAULT_PROFILE, merge_defaults

# Print real de uma BP: pedras com 25 e 100, outra pedra com 100 e um anel.
BP = np.asarray(Image.open(Path(__file__).parent / "assets" / "stack_backpack.png").convert("RGB"))
GRID = [56, 40, 4, 1]
REAL = loot.read_slots(BP, GRID)
SAMPLE = np.asarray(Image.open(Path(__file__).parent / "assets" / "loot_backpack.png").convert("RGB"))
GOLD_82 = loot.read_slots(SAMPLE, [14, 25, 4, 1])[1].pixels
EMPTY = loot.read_slots(SAMPLE, [14, 25, 4, 1])[2].pixels


def test_reads_the_real_grid_of_the_backpack():
    assert loot.find_grid(BP, (52, 36, 150, 40)) == GRID
    assert loot.window_open(BP, GRID)


def test_three_digits_is_a_full_stack():
    assert not stacker.is_full(REAL[0].pixels)  # 25
    assert stacker.is_full(REAL[1].pixels)  # 100
    assert stacker.is_full(REAL[2].pixels)  # 100
    assert not stacker.is_full(GOLD_82)  # 82: tão largo quanto 100, mas são dois algarismos
    assert not stacker.is_full(REAL[3].pixels)  # anel, sem número
    assert not stacker.is_full(EMPTY)


def stack(color, full=False):
    """Item de mentira; o número de 100 vem de uma pilha real."""
    pixels = EMPTY.copy()
    pixels[3:15, 4:28] = color
    if full:
        pixels[stacker.DIGIT_ROWS] = REAL[1].pixels[stacker.DIGIT_ROWS]
    return pixels


RED, BLUE = (200, 40, 40), (40, 60, 200)


def groups(*colors):
    return [[loot.encode_sprite(stack(color))] for color in colors]


class Bag(FakeActionManager):
    """BP de 4 slots: juntar soma na pilha da frente e esvazia (e compacta) a de trás."""

    def __init__(self, items, merges=True, foreground=True):
        super().__init__(foreground=foreground)
        self.items = list(items)  # (cor, cheia)
        self.merges = merges
        self.cursor = (3, 4)

    def frame(self):
        frame = BP.copy()
        for index in range(4):
            left = GRID[0] + index * loot.PITCH
            pixels = stack(*self.items[index]) if index < len(self.items) else EMPTY
            frame[GRID[1]:GRID[1] + loot.SLOT, left:left + loot.SLOT] = pixels
        return frame

    def _index(self, pos):
        return (pos[0] - GRID[0]) // loot.PITCH

    def get_cursor(self):
        return self.cursor

    def drag_with_cursor(self, start, end, quick=False):
        self.calls.append(("drag", self._index(start), self._index(end)))
        return self._merge(start, end)

    def drag(self, start, end, quick=False):
        self.calls.append(("message_drag", self._index(start), self._index(end)))
        return self._merge(start, end)

    def _merge(self, start, end):
        if self.merges:
            source = self.items.pop(self._index(start))
            target = self._index(end)
            self.items[target] = (source[0], True)
        return True


def maker(bag, items):
    profile = merge_defaults(DEFAULT_PROFILE, {"input": {"server_wait": 0.05},
                                               "stacker": {"grid": GRID, "items": items}})
    made = stacker.Stacker(profile, get_frame=bag.frame)
    made.am = bag
    made.alerts, made.logs = [], []
    made.alert, made.log = made.alerts.append, made.logs.append
    return made


def run(made, monkeypatch, idle=0.0):
    monkeypatch.setattr(stacker, "IDLE_SECONDS", idle)
    made._run()
    return made


def test_plan_joins_the_last_open_stack_onto_the_first():
    view = loot.read_slots(Bag([(RED, False), (BLUE, False), (RED, True), (RED, False)]).frame(), GRID)
    source, target, group = stacker.plan(view, groups(RED, BLUE))
    assert (view.index(source), view.index(target), group) == (3, 0, 0)


def test_full_stacks_and_lonely_stacks_are_left_alone():
    view = loot.read_slots(Bag([(RED, True), (RED, False), (BLUE, False)]).frame(), GRID)
    assert stacker.plan(view, groups(RED, BLUE)) is None


def test_items_that_were_not_chosen_are_never_joined():
    view = loot.read_slots(Bag([(BLUE, False), (BLUE, False)]).frame(), GRID)
    assert stacker.plan(view, groups(RED)) is None


def test_a_round_joins_until_nothing_is_left(monkeypatch):
    bag = Bag([(RED, False), (BLUE, False), (RED, False), (BLUE, False)])
    made = run(maker(bag, groups(RED, BLUE)), monkeypatch)

    assert bag.calls == [("drag", 2, 0), ("drag", 2, 1)]
    assert made.merged == 2
    assert not made.alerts
    assert not made.is_running


def test_stops_and_warns_when_the_stacks_do_not_join(monkeypatch):
    bag = Bag([(RED, False), (RED, False)], merges=False)
    made = run(maker(bag, groups(RED)), monkeypatch)

    assert bag.calls == [("drag", 1, 0)]
    assert "não se juntaram" in made.alerts[0]


def test_waits_for_the_mouse_to_stand_still(monkeypatch):
    bag = Bag([(RED, False), (RED, False)])
    positions = iter([(1, 1), (2, 2), (3, 3)])

    def moving():
        return next(positions, (3, 3))
    bag.get_cursor = moving
    clock = {"now": 0.0}
    monkeypatch.setattr(stacker.time, "monotonic", lambda: clock["now"])

    made = maker(bag, groups(RED))
    made._stop_event.wait = lambda seconds: clock.__setitem__("now", clock["now"] + seconds) or False
    run(made, monkeypatch, idle=0.5)

    # Só arrastou depois de o mouse parar: 2 movimentos e meio segundo parado.
    assert bag.calls == [("drag", 1, 0)]
    assert clock["now"] >= 0.5 + 2 * stacker.IDLE_POLL


def test_gives_up_when_the_mouse_never_stops(monkeypatch):
    bag = Bag([(RED, False), (RED, False)])
    counter = iter(range(10 ** 6))
    bag.get_cursor = lambda: (next(counter), 0)
    clock = {"now": 0.0}
    monkeypatch.setattr(stacker.time, "monotonic", lambda: clock["now"])

    made = maker(bag, groups(RED))
    made._stop_event.wait = lambda seconds: clock.__setitem__("now", clock["now"] + seconds) or False
    run(made, monkeypatch, idle=0.5)

    assert bag.calls == []
    assert any("não ficou parado" in message for message in made.logs)


def test_game_behind_goes_by_message_without_waiting_for_the_mouse(monkeypatch):
    """Jogo atrás: mensagem pura, do último slot para o primeiro, sem esperar o mouse parar."""
    bag = Bag([(RED, False), (RED, False)], foreground=False)
    bag.get_cursor = lambda: (_ for _ in ()).throw(AssertionError("não devia olhar o mouse"))
    run(maker(bag, groups(RED)), monkeypatch, idle=99)
    assert bag.calls == [("message_drag", 1, 0)]


def test_without_the_backpack_on_screen_it_does_nothing(monkeypatch):
    bag = Bag([(RED, False), (RED, False)])
    made = maker(bag, groups(RED))
    made.get_frame = lambda: np.zeros_like(BP)
    run(made, monkeypatch)
    assert bag.calls == []
    assert any("não vi a BP" in message for message in made.logs)


def test_reports_what_is_missing():
    made = maker(Bag([]), [])
    assert made.missing() == "os itens"
    made.config["grid"] = None
    assert made.missing() == "os slots da BP"


# Print real: bolts com 40, 1, 2, 3, 4, 5 e 100, e uma comida. Cada quantidade tem um desenho.
BOLTS = np.asarray(Image.open(Path(__file__).parent / "assets" / "stack_bolts.png").convert("RGB"))
BOLTS_GRID = [26, 37, 4, 5]


def test_sizes_captured_as_separate_items_have_nothing_to_join():
    view = loot.read_slots(BOLTS, BOLTS_GRID)
    separate = [[loot.encode_sprite(slot.pixels)] for slot in view[:7]]
    assert stacker.plan(view, separate) is None
    assert "item 1: 1 aberta(s)" in stacker.describe(view, separate)


def test_all_sizes_in_one_item_join_into_the_first_stack():
    view = loot.read_slots(BOLTS, BOLTS_GRID)
    one = [[loot.encode_sprite(slot.pixels) for slot in view[:7]]]
    source, target, group = stacker.plan(view, one)
    assert (view.index(source), view.index(target), group) == (5, 0, 0)
    assert stacker.describe(view, one) == "item 1: 6 aberta(s), 1 cheia(s); 1 slot(s) com itens fora da lista"


def test_a_round_with_nothing_to_join_says_why(monkeypatch):
    bag = Bag([(RED, False), (BLUE, False)])
    made = run(maker(bag, groups(RED, BLUE)), monkeypatch)
    assert bag.calls == []
    assert any("nada a juntar" in message and "+ tamanho" in message for message in made.logs)
