from src.coordinates import CoordinateTransform


def test_coordinate_transform_round_trip():
    coords = CoordinateTransform(window_rect=(100, 50, 1200, 800), dpi_scale=1.0)
    screen = coords.to_screen((200, 150))
    assert screen == (200, 150)
    assert coords.to_window((200, 150)) == (100, 100)
    assert coords.to_logical((200, 150)) == (200, 150)
    assert coords.to_screen(coords.to_window((200, 150))) == (100, 100)


def test_coordinate_transform_handles_dpi_scale():
    coords = CoordinateTransform(window_rect=(0, 0, 1920, 1080), dpi_scale=1.25)
    assert coords.scale_factor == 1.25
    assert coords.to_screen((100, 100)) == (100, 100)
    assert coords.to_window((100, 100)) == (100, 100)
