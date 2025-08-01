# app/utils/logging.py

"""
Logging utilities following SOLID principles.
Provides simple logging functionality for modules that need it.
"""

import logging
from typing import Optional

from app.core.interfaces import ILogger


class UtilsLogger(ILogger):
    """
    Simple logger implementation for utils modules.
    Follows ILogger interface for consistency.
    """

    def __init__(self, name: str = __name__):
        self._logger = logging.getLogger(name)

    def debug(self, message: str) -> None:
        """Log debug message"""
        self._logger.debug(message)

    def info(self, message: str) -> None:
        """Log info message"""
        self._logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message"""
        self._logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message"""
        self._logger.error(message)

    def exception(self, message: str) -> None:
        """Log exception with traceback"""
        self._logger.exception(message)


# Create default logger instance
default_logger = UtilsLogger()


# Export for convenience
def get_logger(name: Optional[str] = None) -> ILogger:
    """Get logger instance"""
    if name:
        return UtilsLogger(name)
    return default_logger
