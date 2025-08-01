# app/core/__init__.py
"""
Core module for dependency injection and application lifecycle management.
"""

from .container import container
from .interfaces import IWorker, IService, IRepository
from .lifecycle import ApplicationLifecycle

__all__ = ["container", "IWorker", "IService", "IRepository", "ApplicationLifecycle"]
