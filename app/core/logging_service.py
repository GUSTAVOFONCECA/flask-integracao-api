# app/core/logging_service.py
"""
Logging service implementing ILogger interface.
Separated from config for Single Responsibility Principle.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask

from .interfaces import ILogger, IConfigProvider


class ColorFormatter(logging.Formatter):
    """Custom formatter with colors and emojis"""

    _COLORS = {
        logging.DEBUG: "\x1b[38;5;244m",  # gray
        logging.INFO: "\x1b[32;20m",  # green
        logging.WARNING: "\x1b[33;20m",  # yellow
        logging.ERROR: "\x1b[31;20m",  # red
        logging.CRITICAL: "\x1b[31;1m",  # red bold
        "reset": "\x1b[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        lvl = record.levelno

        emoji_map = {
            logging.DEBUG: "🐛 ",
            logging.INFO: "ℹ️ ",
            logging.WARNING: "⚠️ ",
            logging.ERROR: "🛑 ",
            logging.CRITICAL: "💥 ",
        }

        color = self._COLORS.get(lvl, "")
        emoji = emoji_map.get(lvl, "")

        base = (
            f"\n{ts} | {record.levelname:<8} | [{record.name}] | "
            f"{record.module}:{record.lineno}\n"
            f"{emoji} {record.getMessage()}\n" + "-" * 80
        )
        return f"{color}{base}{self._COLORS['reset']}"


class FlaskLogger(ILogger):
    """
    Flask-integrated logger implementing ILogger interface.
    Follows Single Responsibility Principle for logging operations.
    """

    def __init__(self, config: IConfigProvider):
        self.config = config
        self._logger = None

    def configure(self, app: Flask) -> None:
        """Configure logging for Flask application"""
        try:
            # Create logs directory
            logs_dir = self.config.get("SYNC_LOG_DIR")
            os.makedirs(logs_dir, exist_ok=True)

            # Setup file handler
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(logs_dir, f"app_{timestamp}.log")

            file_handler = RotatingFileHandler(
                filename=filename,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )

            file_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s | [%(name)s] | %(module)s:%(lineno)d\n"
                "→ %(message)s\n" + ("=" * 100),
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)

            # Setup console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(ColorFormatter())

            # Configure root logger
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.DEBUG)

            # Clear existing handlers
            for h in list(root_logger.handlers):
                root_logger.removeHandler(h)

            # Add new handlers
            root_logger.addHandler(file_handler)
            root_logger.addHandler(console_handler)

            # Quiet verbose libraries
            logging.getLogger("werkzeug").setLevel(logging.WARNING)
            logging.getLogger("urllib3").setLevel(logging.WARNING)

            self._logger = app.logger

            self.info(
                f"🚀 Logging configured successfully\n"
                f"   Environment: {self.config.get('ENV').upper()}\n"
                f"   Log File: {filename}"
            )

        except Exception as e:
            raise RuntimeError(f"Failed to configure logging: {e}") from e

    def info(self, message: str) -> None:
        if self._logger:
            self._logger.info(message)

    def error(self, message: str) -> None:
        if self._logger:
            self._logger.error(message)

    def warning(self, message: str) -> None:
        if self._logger:
            self._logger.warning(message)

    def debug(self, message: str) -> None:
        if self._logger:
            self._logger.debug(message)

    def critical(self, message: str) -> None:
        if self._logger:
            self._logger.critical(message)
