# app/core/__init__.py
"""
Core module for dependency injection and application lifecycle management.
"""

from .container import DIContainer
from .interfaces import IWorker, IService, IRepository
from .lifecycle import ApplicationLifecycle

__all__ = ["DIContainer", "IWorker", "IService", "IRepository", "ApplicationLifecycle"]
