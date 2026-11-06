"""Log em arquivo: sem console (pythonw), é a única forma de ver um erro."""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "exordion.log"


def setup_logging(log_file: Path = LOG_FILE) -> Path:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(threadName)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # pythonw não tem stderr
        root.addHandler(logging.StreamHandler())

    def log_exception(exc_type, exc, tb):
        logging.getLogger("exordion").critical("Erro não tratado", exc_info=(exc_type, exc, tb))

    def log_thread_exception(args):
        logging.getLogger("exordion").critical(
            "Erro não tratado na thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_exception
    threading.excepthook = log_thread_exception
    return log_file
