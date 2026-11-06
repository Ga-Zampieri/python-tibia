import numpy as np

from src.battle_vision import analyze_battle_list, bar_percent, name_signature, signatures_match

GREEN = (0, 200, 0)
RED = (220, 30, 30)
WHITE = (220, 220, 220)
REGION = (0, 0, 200, 240)


def row(frame, y, color=GREEN, text_seed=0, outline=False):
    """Desenha uma linha da battle list: nome em cima, barra de HP embaixo."""
    frame[y + 14:y + 18, 30:130] = color
    rng = np.random.default_rng(text_seed)
    frame[y + 2:y + 12, 30:90][rng.random((10, 60)) > 0.6] = WHITE
    if outline:
        frame[y + 1:y + 2, 0:200] = RED


def blank():
    return np.zeros((240, 200, 3), dtype=np.uint8)


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
