# app/cli/logging_setup.py

import logging
import os
from datetime import datetime
from app.config import Config

def setup_sync_logger():
    """Logger exclusivo para sync, em logs/sync_*.log"""
    log_dir = Config.SYNC_LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(log_dir, f"sync_{ts}.log")

    logger = logging.getLogger("sync_logger")
    # limpa handlers existentes
    if logger.handlers:
        logger.handlers.clear()

    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(path, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # não propaga para root
    logger.propagate = False

    return logger
