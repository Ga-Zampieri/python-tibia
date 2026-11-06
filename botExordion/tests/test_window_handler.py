from src.window_handler import pick_game_window


def test_finds_the_client_and_ignores_lookalikes():
    windows = [
        ("Bot de Tibia OTServ 7.4 - botExordion - Visual Studio Code", 1),
        ("Exordion", 2),
        ("Tibia wiki - Google Chrome", 3),
        ("Tibia", 4),
    ]
    assert pick_game_window(windows) == 4


def test_saved_title_wins():
    windows = [("Tibia", 1), ("Meu Server", 2)]
    assert pick_game_window(windows, "Meu Server") == 2


def test_does_not_guess_between_two_clients():
    assert pick_game_window([("Tibia - A", 1), ("Tibia - B", 2)]) is None
