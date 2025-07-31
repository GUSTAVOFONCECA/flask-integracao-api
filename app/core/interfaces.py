# app/core/interfaces.py
"""
Interfaces and abstract classes for dependency inversion.
Following Interface Segregation Principle (ISP).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
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


class IAuthenticationService(ABC):
    """Interface for authentication services - SRP"""

    @abstractmethod
    def authenticate(self) -> Dict[str, Any]:
        """Authenticate and return tokens"""
        pass

    @abstractmethod
    def refresh_tokens(self) -> Dict[str, Any]:
        """Refresh authentication tokens"""
        pass

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        pass


class IMessageService(ABC):
    """Interface for message sending services - ISP"""

    @abstractmethod
    def send_text_message(self, contact_id: str, message: str) -> Dict[str, Any]:
        """Send text message"""
        pass

    @abstractmethod
    def send_file_message(
        self, contact_id: str, file_content: bytes, filename: str, message: str
    ) -> Dict[str, Any]:
        """Send file message"""
        pass


class ITicketService(ABC):
    """Interface for ticket management services - ISP"""

    @abstractmethod
    def transfer_ticket(
        self, contact_id: str, department_id: str, comments: str
    ) -> Dict[str, Any]:
        """Transfer ticket to department"""
        pass

    @abstractmethod
    def close_ticket(self, contact_id: str) -> Dict[str, Any]:
        """Close ticket"""
        pass

    @abstractmethod
    def has_open_ticket(self, contact_id: str) -> bool:
        """Check if contact has open ticket"""
        pass


class IContactService(ABC):
    """Interface for contact management - SRP"""

    @abstractmethod
    def find_contact_by_phone(self, phone: str) -> Optional[str]:
        """Find contact ID by phone number"""
        pass

    @abstractmethod
    def find_contact_by_document(self, document: str) -> Optional[str]:
        """Find contact ID by document"""
        pass


class ISaleService(ABC):
    """Interface for sales operations - SRP"""

    @abstractmethod
    def create_sale(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sale"""
        pass

    @abstractmethod
    def get_sale_details(self, sale_id: str) -> Dict[str, Any]:
        """Get sale details"""
        pass


class IBillingService(ABC):
    """Interface for billing operations - SRP"""

    @abstractmethod
    def generate_billing(self, sale_id: str) -> Dict[str, Any]:
        """Generate billing for sale"""
        pass

    @abstractmethod
    def get_billing_url(self, sale_id: str) -> Optional[str]:
        """Get billing URL"""
        pass


class ICRMService(ABC):
    """Interface for CRM operations - SRP"""

    @abstractmethod
    def get_item(self, entity_type_id: int, item_id: int) -> Dict[str, Any]:
        """Get CRM item"""
        pass

    @abstractmethod
    def update_item(
        self, entity_type_id: int, item_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update CRM item"""
        pass


class IDataProcessor(ABC):
    """Interface for data processing - SRP"""

    @abstractmethod
    def process_cnpj_data(
        self, cnpj_data: Dict[str, Any], company_id: str
    ) -> Dict[str, Any]:
        """Process CNPJ data for CRM format"""
        pass


class IExternalAPIClient(ABC):
    """Interface for external API clients - DIP"""

    @abstractmethod
    def make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to external API"""
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


class ITokenManager(ABC):
    """Interface for token management - SRP"""

    @abstractmethod
    def save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to storage"""
        pass

    @abstractmethod
    def load_tokens(self) -> Dict[str, Any]:
        """Load tokens from storage"""
        pass

    @abstractmethod
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        pass
