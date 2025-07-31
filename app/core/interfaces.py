# app/core/interfaces.py
"""
Interfaces and abstract classes for dependency inversion.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from flask import Flask


class IConfigProvider(ABC):
    """Interface for configuration providers"""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        pass
    
    @abstractmethod
    def validate(self) -> None:
        """Validate configuration"""
        pass


class ILogger(ABC):
    """Interface for logging services"""
    
    @abstractmethod
    def info(self, message: str) -> None:
        pass
    
    @abstractmethod
    def error(self, message: str) -> None:
        pass
    
    @abstractmethod
    def warning(self, message: str) -> None:
        pass
    
    @abstractmethod
    def debug(self, message: str) -> None:
        pass


class IWorker(ABC):
    """Interface for background workers"""
    
    @abstractmethod
    def start(self) -> None:
        """Start the worker"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the worker"""
        pass
    
    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if worker is healthy"""
        pass


class IService(ABC):
    """Base interface for all services"""
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the service"""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup resources"""
        pass


class IRepository(ABC):
    """Interface for data repositories"""
    
    @abstractmethod
    def save(self, entity: Dict[str, Any]) -> str:
        """Save entity and return ID"""
        pass
    
    @abstractmethod
    def find_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Find entity by ID"""
        pass


class IFlaskAppFactory(ABC):
    """Interface for Flask application factory"""
    
    @abstractmethod
    def create_app(self) -> Flask:
        """Create Flask application instance"""
        pass


class ITunnelService(ABC):
    """Interface for tunnel services"""
    
    @abstractmethod
    def start(self) -> None:
        """Start tunnel service"""
        pass
    
    @abstractmethod
    def get_public_url(self) -> Optional[str]:
        """Get public URL"""
        pass


class IHealthChecker(ABC):
    """Interface for health checking"""
    
    @abstractmethod
    def check_api_health(self) -> bool:
        """Check API health"""
        pass
    
    @abstractmethod
    def check_dependencies(self) -> Dict[str, bool]:
        """Check all dependencies"""
        pass
