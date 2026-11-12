from pathlib import Path

import numpy as np
from PIL import Image

from src import battle_vision
from src.battle_vision import analyze_battle_list, bar_percent, name_signature, signatures_match

GREEN = (0, 188, 0)
RED = (192, 0, 0)
DARK_RED = (96, 0, 0)
WHITE = (192, 192, 192)
BACKGROUND = 30
REGION = (0, 0, 200, 240)
TROLLS = Path(__file__).parent / "assets" / "battle_trolls.png"
TARGET = Path(__file__).parent / "assets" / "battle_target.png"


def read_print(path, allowed=()):
    frame = np.array(Image.open(path).convert("RGB"))
    height, width = frame.shape[:2]
    return analyze_battle_list(frame, (0, 0, width, height), allowed)


def row(frame, y, color=GREEN, text_seed=0, outline=False, percent=100, skull=None):
    """Desenha uma linha da battle list como o cliente: nome em cima e, embaixo,
    a barra de HP com moldura preta e o preenchimento proporcional à vida."""
    frame[y + 13:y + 18, 29:131] = 0
    frame[y + 14:y + 17, 30:130] = BACKGROUND
    frame[y + 14:y + 17, 30:30 + percent] = color
    rng = np.random.default_rng(text_seed)
    text_left = 30 if skull is None else 45
    frame[y + 2:y + 12, text_left:text_left + 60][rng.random((10, 60)) > 0.6] = WHITE
    if skull is not None:
        frame[y + 2:y + 11, 30:40] = skull
        frame[y + 4:y + 9, 32:38] = (150, 150, 150)
    if outline:
        frame[y + 1:y + 2, 0:200] = (220, 30, 30)


def blank():
    return np.full((240, 200, 3), BACKGROUND, dtype=np.uint8)


def test_rows_are_found_with_hp_and_selection():
    frame = blank()
    row(frame, 40)
    row(frame, 70, color=RED, outline=True)

    snapshot = analyze_battle_list(frame, REGION)

    assert [item.hp_state for item in snapshot.rows] == ["green", "red"]
    assert snapshot.selected_index == 1


def test_region_offset_gives_window_coordinates():
    frame = np.zeros((400, 500, 3), dtype=np.uint8)
    row(frame[100:, 200:], 40)

    snapshot = analyze_battle_list(frame, (200, 100, 200, 240))

    left, top, right, _ = snapshot.rows[0].bounds
    assert (left, right) == (200, 400)
    assert top > 100


def test_hp_percent_and_low_hp_colors():
    frame = blank()
    row(frame, 40, color=DARK_RED, percent=5)
    row(frame, 70, color=(192, 192, 0), percent=40)

    rows = analyze_battle_list(frame, REGION).rows

    assert [item.hp_state for item in rows] == ["red", "yellow"]
    assert [item.hp_percent for item in rows] == [5.0, 40.0]


def test_skull_does_not_create_rows_or_change_the_name():
    frame = blank()
    row(frame, 40, text_seed=3)
    row(frame, 70, text_seed=3, skull=(0, 255, 0))
    row(frame, 100, text_seed=3, skull=(200, 8, 10))

    rows = analyze_battle_list(frame, REGION).rows

    assert len(rows) == 3
    assert all(signatures_match(rows[0].signature, item.signature) for item in rows)


def test_real_battle_list_with_skulls_and_outfits():
    """Print do cliente: 7 Trolls, com e sem caveira, outfits diferentes."""
    snapshot = read_print(TROLLS)
    rows = snapshot.rows

    assert snapshot.selected_index is None  # caveira vermelha não é alvo
    assert len(rows) == 7
    assert all(item.hp_state == "green" for item in rows)
    assert all(signatures_match(rows[0].signature, item.signature) for item in rows)
    assert [round(item.hp_percent) for item in rows] == [78, 100, 73, 77, 100, 62, 100]


def test_real_battle_list_with_target_selected():
    """Print do cliente com um Troll sendo atacado: contorno e nome em vermelho."""
    troll = read_print(TROLLS).rows[0].signature

    snapshot = read_print(TARGET, [troll])

    assert snapshot.selected_index == 0
    assert [item.hp_state for item in snapshot.rows] == ["green", "yellow"]
    assert all(item.allowed for item in snapshot.rows)  # nome vermelho continua sendo Troll


def test_name_matches_in_any_color():
    """Cinza normal, branco com o mouse em cima, vermelho/rosa quando é alvo."""
    signatures = []
    for color in (WHITE, (255, 255, 255), (255, 0, 0), (255, 128, 128)):
        frame = blank()
        row(frame, 40, text_seed=5)
        text = frame[42:52, 30:90]
        text[text.max(axis=2) >= 100] = color
        signatures.append(analyze_battle_list(frame, REGION).rows[0].signature)

    assert all(signatures_match(signatures[0], other) for other in signatures)


def test_empty_list_is_not_valid():
    assert analyze_battle_list(blank(), REGION).rows == ()


def test_same_name_matches_regardless_of_position_and_color():
    first, second = blank(), blank()
    row(first, 40, text_seed=7)
    row(second, 100, color=RED, text_seed=7)

    a = analyze_battle_list(first, REGION).rows[0].signature
    b = analyze_battle_list(second, REGION).rows[0].signature

    assert signatures_match(a, b)


def test_different_names_do_not_match():
    first, second = blank(), blank()
    row(first, 40, text_seed=1)
    row(second, 40, text_seed=2)

    a = analyze_battle_list(first, REGION).rows[0].signature
    b = analyze_battle_list(second, REGION).rows[0].signature

    assert not signatures_match(a, b)


def test_rows_outside_the_allowed_names_are_marked():
    frame = blank()
    row(frame, 40, text_seed=1)
    row(frame, 70, text_seed=2)
    known = analyze_battle_list(frame, REGION).rows[0].signature

    rows = analyze_battle_list(frame, REGION, [known]).rows

    assert [item.allowed for item in rows] == [True, False]


def test_signature_of_empty_area_is_empty():
    assert name_signature(np.zeros((10, 10, 3), dtype=np.uint8)) == ""
    assert not signatures_match("", "")


def test_bar_percent_reads_any_color():
    for color in (GREEN, RED, (30, 30, 220)):
        frame = np.zeros((20, 200, 3), dtype=np.uint8)
        frame[5:10, 50:125] = color
        assert bar_percent(frame, (50, 5, 150, 5)) == 50.0


def test_bar_percent_ignores_gray_background():
    frame = np.full((10, 100, 3), 90, dtype=np.uint8)
    assert bar_percent(frame, (0, 0, 100, 10)) == 0.0


def test_bar_percent_without_image():
    assert bar_percent(None, (0, 0, 10, 10)) is None
    assert bar_percent(np.zeros((5, 5, 3), dtype=np.uint8), None) is None


def test_same_image_notices_a_small_sprite():
    empty = np.zeros((24, 24, 3), dtype=np.uint8)
    sprite = empty.copy()
    sprite[8:14, 8:14] = 200

    assert battle_vision.same_image(empty, empty.copy()) is True
    assert battle_vision.same_image(empty, sprite) is False


def test_same_image_ignores_noise_and_rejects_other_sizes():
    empty = np.full((24, 24, 3), 100, dtype=np.uint8)

    assert battle_vision.same_image(empty, empty + 10) is True
    assert battle_vision.same_image(empty, empty[:20]) is False


def test_signature_image_draws_the_saved_name():
    troll = read_print(TROLLS).rows[0].signature
    width, height = (int(v) for v in troll.split(":")[0].split("x"))

    image = battle_vision.signature_image(troll)

    assert image.shape == (height + 4, width + 4, 3)
    assert (image == 220).any() and (image == 30).any()
    assert battle_vision.signature_image("lixo") is None


def test_target_is_found_with_the_mouse_over_it():
    """Com o mouse em cima, o contorno e o nome do alvo ficam rosa (255,136,136);
    sem perceber isso o bot clicava de novo e desligava o ataque."""
    snapshot = read_print(Path(__file__).parent / "assets" / "battle_target_hover.png")
    assert snapshot.selected_index == 0
    assert [round(item.hp_percent) for item in snapshot.rows] == [30, 33]


def test_mouse_over_without_target_is_not_a_target():
    snapshot = read_print(Path(__file__).parent / "assets" / "battle_hover.png")
    assert snapshot.selected_index is None
