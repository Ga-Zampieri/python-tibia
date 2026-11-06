import argparse
import ctypes
import logging

from src.app_log import setup_logging


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()


def run_demo() -> int:
    from src.capture import virtual_screen_bounds
    print("Exordion - verificação rápida")
    print("Desktop virtual (left, top, width, height):", virtual_screen_bounds())
    return 0


def launch_ui() -> None:
    from src.ui import run_ui
    run_ui()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exordion")
    parser.add_argument("--demo", action="store_true", help="verificação rápida, sem interface")
    parser.add_argument("--gui", action="store_true", help="abre a interface (padrão)")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    setup_logging()
    enable_dpi_awareness()
    try:
        launch_ui()
        return 0
    except Exception:
        logging.getLogger("exordion").critical("A interface não abriu", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
