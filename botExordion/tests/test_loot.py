import base64
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import FakeActionManager
from src import loot
from src.settings import DEFAULT_PROFILE, merge_defaults

# Print real de uma backpack do cliente, com um item, ouro (82) e dois slots vazios.
SAMPLE = np.asarray(Image.open(Path(__file__).parent / "assets" / "loot_backpack.png").convert("RGB"))
GRID = [14, 25, 4, 1]
SLOTS = [slot.pixels for slot in loot.read_slots(SAMPLE, GRID)]
ITEM, GOLD, EMPTY = SLOTS[0], SLOTS[1], SLOTS[2]


def sprite(color):
    pixels = EMPTY.copy()
    pixels[4:16, 4:28] = color
    return pixels


BAG = sprite((120, 80, 30))
INSIDE = sprite((30, 90, 200))


class Client(FakeActionManager):
    """Simula um container: tirar um item puxa os seguintes, e a bag abre no lugar."""

    def __init__(self, items, bag_contents=(), bag_opens=True, can_move=True, foreground=False):
        super().__init__(foreground=foreground)
        self.window_open = True
        self.items = list(items)
        self.bag_contents = list(bag_contents)
        self.bag_opens = bag_opens
        self.can_move = can_move
        self.received = []
        self.speeds = []
        self.refuses_quick = False

    def frame(self):
        if not self.window_open:
            return np.zeros((80, 180, 3), dtype=np.uint8)
        frame = SAMPLE.copy()
        for index in range(4):
            pixels = self.items[index] if index < len(self.items) else EMPTY
            left = GRID[0] + index * loot.PITCH
            frame[GRID[1]:GRID[1] + loot.SLOT, left:left + loot.SLOT] = pixels
        return frame

    def _index(self, pos):
        return (pos[0] - GRID[0]) // loot.PITCH

    def drag(self, start, end):
        super().drag(start, end)
        if self.can_move:
            self.received.append(self.items.pop(self._index(start)))
        return True

    def right_click(self, pos):
        super().right_click(pos)
        if self.bag_opens:
            self.items = list(self.bag_contents)
        return True

    def drag_with_cursor(self, start, end, quick=False):
        super().drag_with_cursor(start, end)
        self.speeds.append(quick)
        if self.can_move and not (quick and self.refuses_quick):
            self.received.append(self.items.pop(self._index(start)))
        return True

    def press_with_cursor(self, pos, button):
        super().press_with_cursor(pos, button)
        if button == "right" and self.bag_opens:
            self.items = list(self.bag_contents)


CLOSE = [168, 12]


def looter(client, items=(GOLD, ITEM), bags=(BAG,), close=None):
    profile = merge_defaults(DEFAULT_PROFILE, {"loot": {
        "grid": GRID, "destination": [500, 500], "close": close,
        "items": [loot.encode_sprite(pixels) for pixels in items],
        "bags": [loot.encode_sprite(pixels) for pixels in bags],
    }})
    maker = loot.Looter(profile, get_frame=client.frame)
    maker.am = client
    maker.alerts = []
    maker.alert = maker.alerts.append
    maker.logs = []
    maker.log = maker.logs.append
    maker._stop_event.wait = lambda _seconds: False
    return maker


def run(maker):
    maker._run()
    return maker


@pytest.mark.parametrize("rect", [(14, 25, 143, 32), (11, 22, 148, 38), (18, 28, 136, 26)])
def test_grid_fits_a_rough_selection_of_the_real_client(rect):
    assert loot.find_grid(SAMPLE, rect) == GRID


def test_real_slots_are_told_apart():
    assert [loot.is_empty(pixels) for pixels in SLOTS] == [False, False, True, True]
    assert not loot.same_item(ITEM, GOLD)


def test_stack_number_does_not_change_the_item():
    other_amount = GOLD.copy()
    other_amount[19:29, 12:31] = (240, 240, 240)
    assert loot.same_item(GOLD, other_amount)


def test_sprite_survives_being_saved():
    assert np.array_equal(loot.decode_sprite(loot.encode_sprite(GOLD)), GOLD)


def test_takes_what_was_learned_and_leaves_the_rest():
    unwanted = sprite((200, 30, 30))
    client = Client([unwanted, GOLD, ITEM])

    maker = run(looter(client))

    assert maker.taken == 2
    assert [item is GOLD or item is ITEM for item in client.received] == [True, True]
    assert len(client.items) == 1 and client.items[0] is unwanted
    assert maker.alerts == []


def test_two_equal_items_side_by_side_are_both_taken():
    client = Client([GOLD, GOLD, GOLD])

    assert run(looter(client)).taken == 3
    assert client.items == []


def test_drags_from_slot_center_to_destination():
    client = Client([GOLD])
    run(looter(client))
    assert client.calls == [("drag", (30, 41), (500, 500))]


def test_opens_bag_after_the_loose_items_and_takes_its_contents():
    client = Client([BAG, GOLD], bag_contents=[ITEM, GOLD])

    maker = run(looter(client))

    assert maker.taken == 3
    assert [call[0] for call in client.calls] == ["drag", "right", "drag", "drag"]
    assert client.items == []


def test_bag_inside_bag():
    client = Client([BAG, sprite((200, 30, 30))], bag_contents=[BAG])
    maker = looter(client)
    maker._step()
    client.bag_contents = [GOLD]

    assert run(maker).taken == 1


def test_stops_and_warns_when_item_does_not_move():
    client = Client([GOLD, ITEM], can_move=False)

    maker = run(looter(client))

    assert maker.taken == 0
    assert len(client.calls) == 1
    assert "mochila cheia" in maker.alerts[0]


def test_warns_when_bag_does_not_open_in_the_same_window():
    client = Client([BAG], bag_opens=False)

    maker = run(looter(client))

    assert len(client.calls) == 1
    assert "bag" in maker.alerts[0]


def test_no_input_block_means_no_action():
    client = Client([GOLD])
    client.block_ok = False

    maker = run(looter(client))

    assert client.calls == []
    assert maker.taken == 0


def test_nothing_learned_in_view_does_nothing():
    client = Client([sprite((200, 30, 30))])
    maker = run(looter(client))
    assert client.calls == []
    assert maker.logs == ["Loot: 0 item(ns) pego(s)."]


def test_without_image_it_does_nothing():
    client = Client([GOLD])
    maker = looter(client)
    maker.get_frame = lambda: None

    run(maker)

    assert client.calls == []


def test_step_limit_ends_a_container_that_never_empties():
    class Endless(Client):
        def drag(self, start, end):
            self.calls.append(("drag",))
            self.items = [ITEM if self.items[0] is GOLD else GOLD]
            return True

    client = Endless([GOLD])
    run(looter(client))
    assert len(client.calls) == loot.MAX_STEPS


def test_reports_what_is_missing():
    profile = merge_defaults(DEFAULT_PROFILE, {})
    maker = loot.Looter(profile)
    assert maker.missing() == "os slots do loot"
    profile["loot"]["grid"] = GRID
    assert maker.missing() == "o destino"
    profile["loot"]["destination"] = [1, 2]
    assert maker.missing() == "os itens"
    profile["loot"]["bags"] = ["x"]
    assert maker.missing() == ""


def test_grid_with_several_rows():
    frame = np.zeros((130, 178, 3), dtype=np.uint8)
    frame[:73] = SAMPLE
    frame[61:99] = SAMPLE[24:62]

    assert loot.find_grid(frame, (14, 25, 143, 69)) == [14, 25, 4, 2]


def test_selection_without_slots_is_refused():
    assert loot.find_grid(np.full((100, 100, 3), 40, dtype=np.uint8), (10, 10, 60, 60)) is None
    assert loot.find_grid(SAMPLE, (14, 25, 10, 10)) is None


def test_game_in_front_uses_the_real_cursor_and_gives_it_back():
    client = Client([BAG, GOLD], bag_contents=[ITEM], foreground=True)

    maker = run(looter(client, close=CLOSE))

    assert maker.taken == 2
    kinds = [call[0] for call in client.calls]
    assert "drag" not in kinds and "right" not in kinds and "left" not in kinds
    assert kinds.count("drag_cursor") == 2
    assert ("cursor_click", "right", (30, 41)) in client.calls
    assert client.calls[-2:] == [("cursor_click", "left", tuple(CLOSE)), ("cursor", (3, 4))]


def test_game_behind_uses_messages():
    client = Client([GOLD])
    maker = looter(client, close=CLOSE)
    run(maker)
    assert client.calls == [("drag", (30, 41), (500, 500)), ("left", tuple(CLOSE))]


def test_closes_a_corpse_that_only_has_unwanted_items():
    client = Client([sprite((200, 30, 30))])
    run(looter(client, close=CLOSE))
    assert client.calls == [("left", tuple(CLOSE))]


def test_without_close_point_the_window_stays():
    client = Client([GOLD])
    run(looter(client))
    assert [call[0] for call in client.calls] == ["drag"]


def test_does_not_click_x_when_no_window_is_there():
    client = Client([])
    client.window_open = False
    run(looter(client, close=CLOSE))
    assert client.calls == []


def test_failed_loot_keeps_the_window_open():
    client = Client([GOLD], can_move=False)
    run(looter(client, close=CLOSE))
    assert [call[0] for call in client.calls] == ["drag"]


def test_cancelled_loot_keeps_the_window_open():
    client = Client([GOLD, ITEM])
    maker = looter(client, close=CLOSE)
    answers = iter([True])
    maker._stop_event.wait = lambda _seconds: next(answers)

    run(maker)

    assert [call[0] for call in client.calls] == ["drag"]


def test_step_limit_does_not_close():
    class Endless(Client):
        def drag(self, start, end):
            self.calls.append(("drag",))
            self.items = [ITEM if self.items[0] is GOLD else GOLD]
            return True

    client = Endless([GOLD])
    run(looter(client, close=CLOSE))
    assert ("left", tuple(CLOSE)) not in client.calls


def test_second_bag_keeps_the_window_open_and_says_so():
    client = Client([BAG, BAG], bag_contents=[GOLD])

    maker = run(looter(client, close=CLOSE))

    assert maker.taken == 1
    assert ("left", tuple(CLOSE)) not in client.calls
    assert any("ficado loot" in message for message in maker.logs)


def test_real_print_counts_as_an_open_window():
    assert loot.window_open(SAMPLE, GRID)
    assert not loot.window_open(SAMPLE, [20, 25, 4, 1])
    assert not loot.window_open(np.zeros((80, 180, 3), dtype=np.uint8), GRID)


# Print real de uma backpack rolando: 5 quadros seguidos, um por clique na seta.
SCROLL_FRAMES = np.asarray(Image.open(Path(__file__).parent / "assets" / "loot_scroll.png").convert("RGB")).reshape(5, 67, 178, 3)
SCROLL_GRID = [14, 22, 4, 1]


def test_measures_the_shift_of_each_real_scroll_step():
    assert [loot.row_shift(frame, SCROLL_GRID) for frame in SCROLL_FRAMES] == [0, 14, 28, 5, 19]


def test_reads_only_the_rows_that_are_visible_enough():
    tops = [sorted({slot.top for slot in loot.read_view(frame, SCROLL_GRID)}) for frame in SCROLL_FRAMES]
    assert tops == [[22], [], [31], [17], []]
    assert all(loot.is_empty(slot.pixels) for slot in loot.read_view(SCROLL_FRAMES[3], SCROLL_GRID))


def test_recognizes_a_cut_item():
    gold = SCROLL_FRAMES[0][22:54, 14:46]
    visible = SCROLL_FRAMES[1][17:40, 14:46]  # quadro seguinte: 14 px rolados, 9 linhas cortadas
    assert loot.same_item(visible, gold, skip=9)
    assert not loot.same_item(visible, ITEM, skip=9)


def test_scroll_arrows_are_where_the_real_click_worked():
    assert loot.scroll_point([1756, 577, 4, 1], True) == (1910, 606)
    assert loot.scroll_point([1756, 577, 4, 1], False) == (1910, 578)


class ScrollClient(Client):
    """Janela de uma fileira sobre um corpo maior, rolando 14 px como o cliente real."""

    STEP = 14
    PERIOD = SAMPLE[21:58]

    def __init__(self, items, rows, closes=True, **kwargs):
        super().__init__(items, **kwargs)
        self.rows = rows
        self.closes = closes
        self.offset = 0

    def frame(self):
        if not self.window_open:
            return np.zeros((80, 180, 3), dtype=np.uint8)
        canvas = np.vstack([self.PERIOD[:1]] + [self.PERIOD] * self.rows + [self.PERIOD[:4]])
        for index in range(self.rows * 4):
            left = GRID[0] + index % 4 * loot.PITCH
            top = 5 + index // 4 * loot.PITCH
            pixels = self.items[index] if index < len(self.items) else EMPTY
            canvas[top:top + loot.SLOT, left:left + loot.SLOT] = pixels
        frame = SAMPLE.copy()
        frame[GRID[1] - 5:GRID[1] + 36] = canvas[self.offset:self.offset + 41]
        return frame

    def _index(self, pos):
        row = (pos[1] - GRID[1] + self.offset) // loot.PITCH
        return row * 4 + (pos[0] - GRID[0]) // loot.PITCH

    def left_click(self, pos):
        super().left_click(pos)
        limit = (self.rows - 1) * loot.PITCH
        if tuple(pos) == loot.scroll_point(GRID, True):
            self.offset = min(self.offset + self.STEP, limit)
        elif tuple(pos) == loot.scroll_point(GRID, False):
            self.offset = max(self.offset - self.STEP, 0)
        elif tuple(pos) == tuple(CLOSE) and self.closes:
            self.window_open = False
        return True


JUNK = [sprite((200, 30, 30)), sprite((30, 200, 30)), sprite((200, 200, 30)), sprite((200, 30, 200))]


def clicks(client, point):
    return client.calls.count(("left", tuple(point)))


def test_scrolls_to_find_what_is_below_the_visible_row():
    client = ScrollClient(JUNK + [GOLD], rows=2)

    maker = run(looter(client, close=CLOSE))

    assert maker.taken == 1
    assert client.items == JUNK
    assert clicks(client, loot.scroll_point(GRID, True)) >= 1
    assert not client.window_open


def test_scrolls_through_several_rows():
    client = ScrollClient(JUNK * 2 + [ITEM, GOLD], rows=3)
    assert run(looter(client, close=CLOSE)).taken == 2
    assert not client.window_open


def test_full_corpse_without_more_rows_still_closes():
    client = ScrollClient(JUNK, rows=1)

    run(looter(client, close=CLOSE))

    assert clicks(client, loot.scroll_point(GRID, True)) == 1
    assert not client.window_open


def test_empty_slot_means_nothing_below_and_no_scroll():
    client = ScrollClient(JUNK[:3], rows=2)
    run(looter(client, close=CLOSE))
    assert clicks(client, loot.scroll_point(GRID, True)) == 0


def test_bag_in_a_full_view_may_hide_loot_so_the_window_stays():
    client = ScrollClient(JUNK[:3] + [BAG, GOLD], rows=2, bag_contents=[ITEM])

    maker = run(looter(client, close=CLOSE))

    assert client.window_open
    assert any("ficado loot" in message for message in maker.logs)


def test_opening_a_bag_after_scrolling_goes_back_to_the_top():
    client = ScrollClient(JUNK + [BAG], rows=2, bag_contents=[GOLD])

    maker = run(looter(client))

    assert maker.taken == 1
    assert client.offset == 0
    assert clicks(client, loot.scroll_point(GRID, False)) >= 1


def test_warns_when_the_x_does_not_close():
    client = ScrollClient([GOLD], rows=1, closes=False)
    maker = run(looter(client, close=CLOSE))
    assert any("continuou aberta" in message for message in maker.logs)


def test_warns_when_no_window_was_there_to_close():
    client = Client([])
    client.window_open = False
    maker = run(looter(client, close=CLOSE))
    assert any("não cliquei no X" in message for message in maker.logs)


def test_game_in_front_drags_quickly():
    client = Client([GOLD, ITEM], foreground=True)
    assert run(looter(client)).taken == 2
    assert client.speeds == [True, True]


def test_falls_back_to_the_normal_drag_when_the_quick_one_is_refused():
    client = Client([GOLD, ITEM], foreground=True)
    client.refuses_quick = True

    maker = run(looter(client))

    assert maker.taken == 2
    assert client.speeds == [True, False, False]
    assert maker.alerts == []
    assert any("arraste rápido" in message for message in maker.logs)


def test_full_backpack_does_not_turn_off_the_quick_drag():
    client = Client([GOLD], can_move=False, foreground=True)

    maker = run(looter(client))

    assert client.speeds == [True, False]
    assert maker._quick
    assert "mochila cheia" in maker.alerts[0]


def config_with(items=(), bags=()):
    return {"items": [loot.encode_sprite(pixels) for pixels in items],
            "bags": [loot.encode_sprite(pixels) for pixels in bags], "routes": {}}


def test_list_keeps_only_the_sprites():
    config = {**config_with([GOLD], [BAG]), "grid": GRID, "destination": [1, 2], "close": [3, 4]}
    assert set(loot.export_list(config)) == {"format", "version", "items", "bags", "routes"}


def test_import_adds_to_the_list_without_repeating():
    mine = config_with([GOLD])
    shared = loot.export_list(config_with([GOLD, ITEM], [BAG]))

    assert loot.import_list(mine, shared) == 2
    assert len(mine["items"]) == 2 and len(mine["bags"]) == 1
    assert loot.import_list(mine, shared) == 0


def test_import_does_not_repeat_inside_the_file():
    mine = config_with()
    shared = loot.export_list(config_with([GOLD, GOLD]))
    assert loot.import_list(mine, shared) == 1


@pytest.mark.parametrize("data", [
    None,
    [],
    {"items": []},
    {"format": "outro", "items": []},
    {"format": loot.LIST_FORMAT, "items": "abc"},
    {"format": loot.LIST_FORMAT, "items": [1]},
    {"format": loot.LIST_FORMAT, "routes": []},
    {"format": loot.LIST_FORMAT, "routes": {"x": -1}},
    {"format": loot.LIST_FORMAT, "routes": {"x": "2"}},
    {"format": loot.LIST_FORMAT, "routes": {"x": True}},
    {"format": loot.LIST_FORMAT, "items": ["não é base64"]},
    {"format": loot.LIST_FORMAT, "items": [base64.b64encode(zlib.compress(b"x" * 10)).decode()]},
    {"format": loot.LIST_FORMAT, "items": [base64.b64encode(zlib.compress(bytes(10 ** 7))).decode()]},
])
def test_import_refuses_what_is_not_a_list_and_changes_nothing(data):
    mine = config_with([GOLD])
    assert loot.import_list(mine, data) is None
    assert len(mine["items"]) == 1 and mine["bags"] == []


BP2, BP3 = [600, 600], [700, 700]


def routed(client, routes, extra=(BP2, BP3)):
    maker = looter(client)
    maker.config["extra_destinations"] = [list(point) for point in extra]
    maker.config["routes"] = {loot.encode_sprite(pixels): index for pixels, index in routes}
    return maker


def test_each_item_goes_to_its_own_backpack():
    client = Client([GOLD, ITEM])
    run(routed(client, [(ITEM, 2)]))
    assert [call[2] for call in client.calls] == [(500, 500), (700, 700)]


def test_item_without_route_goes_to_the_first_backpack():
    client = Client([ITEM])
    run(routed(client, []))
    assert client.calls[0][2] == (500, 500)


def test_route_to_a_backpack_that_does_not_exist_uses_the_first():
    client = Client([ITEM])
    run(routed(client, [(ITEM, 5)]))
    assert client.calls[0][2] == (500, 500)


def test_route_works_with_a_cut_item_after_scrolling():
    gold = loot.encode_sprite(GOLD)
    config = {"destination": [1, 1], "extra_destinations": [BP2], "routes": {gold: 1}, "items": [gold]}
    cut = GOLD[9:]
    sprite = loot.match(cut, config["items"], 9)
    assert loot.destinations(config)[loot.destination_of(config, sprite)] == BP2


def test_removing_a_backpack_sends_its_items_to_the_first_and_renumbers():
    config = {"destination": [1, 1], "extra_destinations": [[2, 2], [3, 3]], "routes": {"a": 1, "b": 2}}

    loot.remove_destination(config, 1)

    assert config["extra_destinations"] == [[3, 3]]
    assert config["routes"] == {"b": 1}


def test_shared_list_keeps_the_backpack_of_each_item():
    source = config_with([GOLD, ITEM])
    loot.set_route(source, source["items"][1], 2)
    mine = config_with()

    assert loot.import_list(mine, loot.export_list(source)) == 2
    assert mine["routes"] == {source["items"][1]: 2}


def test_import_does_not_change_the_route_of_an_item_i_already_have():
    mine = config_with([GOLD])
    shared = config_with([GOLD])
    loot.set_route(shared, shared["items"][0], 3)

    assert loot.import_list(mine, loot.export_list(shared)) == 0
    assert mine["routes"] == {}


def test_old_list_without_routes_still_imports():
    mine = config_with()
    old = {"format": loot.LIST_FORMAT, "version": 1, "items": config_with([GOLD])["items"], "bags": []}
    assert loot.import_list(mine, old) == 1
