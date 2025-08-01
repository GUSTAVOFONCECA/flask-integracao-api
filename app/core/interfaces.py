# app/core/interfaces.py
"""
Interfaces following Interface Segregation Principle (ISP).
Each interface has a single, focused responsibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol
import logging


# Core service interfaces
class IConfigProvider(Protocol):
    """Interface for configuration providers"""

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        ...

    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        ...


class ILogger(Protocol):
    """Interface for logging services"""

    def get_logger(self, name: str) -> logging.Logger:
        """Get logger by name"""
        ...

    def setup(self) -> None:
        """Setup logging configuration"""
        ...


class IHealthChecker(Protocol):
    """Interface for health checking"""

    def check_health(self) -> bool:
        """Check if service is healthy"""
        ...


# Authentication interfaces
class IAuthenticationService(Protocol):
    """Interface for authentication services"""

    def authenticate(self) -> bool:
        """Authenticate with the service"""
        ...

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        ...


class ITokenManager(Protocol):
    """Interface for token management"""

    def get_token(self, service: str) -> Optional[str]:
        """Get token for service"""
        ...

    def refresh_token(self, service: str) -> bool:
        """Refresh token for service"""
        ...


# Business service interfaces
class IMessageService(Protocol):
    """Interface for message services"""

    def send_message(self, recipient: str, message: str) -> bool:
        """Send a message"""
        ...


class ITicketService(Protocol):
    """Interface for ticket services"""

    def create_ticket(self, data: Dict[str, Any]) -> Optional[str]:
        """Create a ticket"""
        ...

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Get ticket by ID"""
        ...


class IContactService(Protocol):
    """Interface for contact services"""

    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create a contact"""
        ...

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get contact by ID"""
        ...


class ISaleService(Protocol):
    """Interface for sales services"""

    def create_sale(self, sale_data: Dict[str, Any]) -> Optional[str]:
        """Create a sale"""
        ...


class IBillingService(Protocol):
    """Interface for billing services"""

    def create_invoice(self, invoice_data: Dict[str, Any]) -> Optional[str]:
        """Create an invoice"""
        ...


class ICRMService(Protocol):
    """Interface for CRM services"""

    def create_lead(self, lead_data: Dict[str, Any]) -> Optional[str]:
        """Create a lead"""
        ...


# Worker interfaces
class IWorker(ABC):
    """Base interface for workers"""

    @abstractmethod
    def start(self) -> None:
        """Start the worker"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the worker"""
        pass


class IScheduledWorker(IWorker):
    """Interface for scheduled workers"""

    @abstractmethod
    def run(self) -> None:
        """Execute the worker's logic"""
        pass


# Service lifecycle interfaces
class IService(ABC):
    """Base interface for services"""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the service"""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup service resources"""
        pass


class IRepository(ABC):
    """Base interface for repositories"""

    @abstractmethod
    def get(self, id: str) -> Optional[Any]:
        """Get entity by ID"""
        pass

    @abstractmethod
    def save(self, entity: Any) -> str:
        """Save entity"""
        pass