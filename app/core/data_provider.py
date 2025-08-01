# app/core/data_provider.py

"""
Data Provider following SOLID principles.
Implements Single Responsibility and Dependency Inversion.
"""

import logging
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class IDataProvider(ABC):
    """Interface for data providers"""

    @abstractmethod
    def get_connection(self):
        """Get database connection"""
        ...

    @abstractmethod
    def execute_query(self, query: str, params: tuple = None) -> Any:
        """Execute database query"""
        ...


class DatabaseProvider(IDataProvider):
    """
    Database provider implementation.
    Follows Single Responsibility Principle.
    """

    def __init__(self, config_provider):
        self._config = config_provider

    def get_connection(self):
        """Get database connection"""
        from app.database.database import get_db_connection

        return get_db_connection()

    def execute_query(self, query: str, params: tuple = None) -> Any:
        """Execute database query"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params or ())
            return cursor.fetchall()
