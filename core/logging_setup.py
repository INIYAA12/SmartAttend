"""Structured application logging: console + rotating file (logs/app.log)."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ROOT_NAME = "smartattendance"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging():
    """Idempotent -- safe to call from every create_app()."""
    logger = logging.getLogger(ROOT_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(console)

    if config.LOG_TO_FILE:
        try:
            os.makedirs(config.LOG_DIR, exist_ok=True)
            fh = RotatingFileHandler(os.path.join(config.LOG_DIR, "app.log"),
                                     maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            fh.setFormatter(logging.Formatter(_FORMAT))
            logger.addHandler(fh)
        except OSError:
            logger.warning("Could not open log file in %s; logging to console only.", config.LOG_DIR)
    return logger


def get_logger(name):
    return logging.getLogger(f"{ROOT_NAME}.{name}")
