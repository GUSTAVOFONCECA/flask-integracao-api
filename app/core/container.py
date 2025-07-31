# app/core/container.py
"""
Dependency Injection Container implementing Service Locator pattern.
"""

from typing import Dict, Any, Type, Callable, TypeVar, Optional
from functools import wraps
import threading

T = TypeVar("T")


class DIContainer:
    """
    Thread-safe dependency injection container.
    Manages service lifecycles and dependency resolution.
    """

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_singleton(
        self, interface: Type[T], implementation: Type[T]
    ) -> "DIContainer":
        """Register a singleton service"""
        with self._lock:
            key = self._get_key(interface)
            self._factories[key] = lambda: implementation()
            return self

    def register_factory(
        self, interface: Type[T], factory: Callable[[], T]
    ) -> "DIContainer":
        """Register a factory function"""
        with self._lock:
            key = self._get_key(interface)
            self._factories[key] = factory
            return self

    def register_instance(self, interface: Type[T], instance: T) -> "DIContainer":
        """Register an existing instance"""
        with self._lock:
            key = self._get_key(interface)
            self._singletons[key] = instance
            return self

    def resolve(self, interface: Type[T]) -> T:
        """Resolve a service by interface"""
        key = self._get_key(interface)

        # Check if already instantiated singleton
        if key in self._singletons:
            return self._singletons[key]

        # Check if factory exists
        if key not in self._factories:
            raise KeyError(f"Service not registered: {key}")

        with self._lock:
            # Double-check pattern for thread safety
            if key in self._singletons:
                return self._singletons[key]

            # Create instance
            instance = self._factories[key]()
            self._singletons[key] = instance
            return instance

    def try_resolve(self, interface: Type[T]) -> Optional[T]:
        """Try to resolve a service, return None if not found"""
        try:
            return self.resolve(interface)
        except KeyError:
            return None

    def is_registered(self, interface: Type[T]) -> bool:
        """Check if a service is registered"""
        key = self._get_key(interface)
        return key in self._factories or key in self._singletons

    def clear(self) -> None:
        """Clear all registrations"""
        with self._lock:
            self._services.clear()
            self._factories.clear()
            self._singletons.clear()

    @staticmethod
    def _get_key(interface: Type) -> str:
        """Get unique key for interface"""
        return f"{interface.__module__}.{interface.__name__}"


# Global container instance
container = DIContainer()


def inject(interface: Type[T]) -> Callable:
    """Decorator for dependency injection"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            service = container.resolve(interface)
            return func(service, *args, **kwargs)

        return wrapper

    return decorator
