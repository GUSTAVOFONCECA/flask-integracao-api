# app/core/interfaces.py

"""
Core interfaces following SOLID principles.
Implements Interface Segregation and Dependency Inversion.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Union


# Core Infrastructure Interfaces
class ILogger(Protocol):
    """Interface for logging operations"""
    
    def debug(self, message: str) -> None:
        """Log debug message"""
        ...
    
    def info(self, message: str) -> None:
        """Log info message"""
        ...
    
    def warning(self, message: str) -> None:
        """Log warning message"""
        ...
    
    def error(self, message: str) -> None:
        """Log error message"""
        ...
    
    def exception(self, message: str) -> None:
        """Log exception with traceback"""
        ...


class IConfigProvider(Protocol):
    """Interface for configuration providers"""
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        ...
    
    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        ...
    
    def has(self, key: str) -> bool:
        """Check if configuration key exists"""
        ...


class IHealthChecker(Protocol):
    """Interface for health checking"""
    
    def check_health(self) -> Dict[str, Any]:
        """Check system health"""
        ...
    
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        ...


class IWorker(Protocol):
    """Interface for background workers"""
    
    def start(self) -> None:
        """Start the worker"""
        ...
    
    def stop(self) -> None:
        """Stop the worker"""
        ...


class IService(Protocol):
    """Interface for application services"""
    
    def initialize(self) -> None:
        """Initialize the service"""
        ...
    
    def cleanup(self) -> None:
        """Cleanup service resources"""
        ...


# Authentication and Authorization Interfaces
class ITokenManager(Protocol):
    """Interface for token management"""
    
    def get_access_token(self) -> Optional[str]:
        """Get current access token"""
        ...
    
    def get_refresh_token(self) -> Optional[str]:
        """Get current refresh token"""
        ...
    
    def save_tokens(self, access_token: str, refresh_token: str = None, expires_in: int = None) -> None:
        """Save tokens"""
        ...
    
    def is_token_valid(self) -> bool:
        """Check if current token is valid"""
        ...
    
    def clear_tokens(self) -> None:
        """Clear stored tokens"""
        ...


"""
Core interfaces following SOLID principles.
Defines contracts for all services in the application.
"""

from typing import Dict, Any, Optional, Protocol
from abc import ABC, abstractmethod


class IAuthenticationService(Protocol):
    """Interface for authentication services"""
    
    def authenticate(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Authenticate with credentials"""
        ...
    
    def refresh_token(self) -> Dict[str, Any]:
        """Refresh authentication token"""
        ...
    
    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        ...


# Communication Services Interfaces
class IMessageService(Protocol):
    """Interface for message services"""
    
    def send_message(self, contact_id: str, message: str, **kwargs) -> Dict[str, Any]:
        """Send a message"""
        ...
    
    def send_file(self, contact_id: str, file_path: str, **kwargs) -> Dict[str, Any]:
        """Send a file"""
        ...
    
    def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """Get message status"""
        ...


class ITicketService(Protocol):
    """Interface for ticket services"""
    
    def create_ticket(self, contact_id: str, subject: str, **kwargs) -> Dict[str, Any]:
        """Create a ticket"""
        ...
    
    def update_ticket(self, ticket_id: str, **kwargs) -> Dict[str, Any]:
        """Update a ticket"""
        ...
    
    def close_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Close a ticket"""
        ...
    
    def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Get ticket details"""
        ...


class IContactService(Protocol):
    """Interface for contact services"""
    
    def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a contact"""
        ...
    
    def update_contact(self, contact_id: str, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a contact"""
        ...
    
    def find_contact_by_phone(self, phone: str) -> Optional[str]:
        """Find contact by phone number"""
        ...
    
    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get contact details"""
        ...


class IBillingService(Protocol):
    """Interface for billing services"""
    
    def create_bill(self, bill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a bill"""
        ...
    
    def get_bill(self, bill_id: str) -> Dict[str, Any]:
        """Get bill details"""
        ...


class ICRMService(Protocol):
    """Interface for CRM services"""
    
    def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a lead"""
        ...
    
    def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a lead"""
        ...


class ITokenManager(Protocol):
    """Interface for token management"""
    
    def get_token(self, service: str) -> Optional[str]:
        """Get token for service"""
        ...
    
    def refresh_token(self, service: str) -> bool:
        """Refresh token for service"""
        ...


class ILogger(Protocol):
    """Interface for logging services"""
    
    def debug(self, message: str) -> None:
        """Log debug message"""
        ...
    
    def info(self, message: str) -> None:
        """Log info message"""
        ...
    
    def warning(self, message: str) -> None:
        """Log warning message"""
        ...
    
    def error(self, message: str) -> None:
        """Log error message"""
        ...
    
    def exception(self, message: str) -> None:
        """Log exception with traceback"""
        ...
    
    def get_logger(self, name: str):
        """Get logger by name"""
        ...


class IWorker(Protocol):
    """Interface for worker services"""
    
    def start(self) -> None:
        """Start the worker"""
        ...
    
    def stop(self) -> None:
        """Stop the worker"""
        ...


class IConfigProvider(Protocol):
    """Interface for configuration providers"""
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        ...
    
    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        ...
    
    def items(self) -> Dict[str, Any]:
        """Get all configuration items"""
        ...


# Business Services Interfaces
class ISaleService(Protocol):
    """Interface for sales services"""
    
    def create_sale(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a sale"""
        ...
    
    def update_sale(self, sale_id: str, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a sale"""
        ...
    
    def get_sale(self, sale_id: str) -> Dict[str, Any]:
        """Get sale details"""
        ...
    
    def cancel_sale(self, sale_id: str) -> Dict[str, Any]:
        """Cancel a sale"""
        ...


class IBillingService(Protocol):
    """Interface for billing services"""
    
    def create_bill(self, bill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a bill"""
        ...
    
    def update_bill(self, bill_id: str, bill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a bill"""
        ...
    
    def get_bill(self, bill_id: str) -> Dict[str, Any]:
        """Get bill details"""
        ...
    
    def send_bill(self, bill_id: str, contact_info: Dict[str, Any]) -> Dict[str, Any]:
        """Send bill to contact"""
        ...


class ICRMService(Protocol):
    """Interface for CRM services"""
    
    def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a lead"""
        ...
    
    def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a lead"""
        ...
    
    def get_lead(self, lead_id: str) -> Dict[str, Any]:
        """Get lead details"""
        ...
    
    def convert_lead(self, lead_id: str) -> Dict[str, Any]:
        """Convert lead to customer"""
        ...


# Data Processing Interfaces
class IDataProcessor(Protocol):
    """Interface for data processors"""
    
    def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data"""
        ...
    
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """Validate data"""
        ...
    
    def transform_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform data"""
        ...


class IExternalAPIClient(Protocol):
    """Interface for external API clients"""
    
    def make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request"""
        ...
    
    def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make GET request"""
        ...
    
    def post(self, endpoint: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Make POST request"""
        ...
    
    def put(self, endpoint: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Make PUT request"""
        ...
    
    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request"""
        ...


# Repository Interfaces
class IRepository(Protocol):
    """Base repository interface"""
    
    def save(self, entity: Any) -> Any:
        """Save entity"""
        ...
    
    def find_by_id(self, entity_id: str) -> Optional[Any]:
        """Find entity by ID"""
        ...
    
    def update(self, entity_id: str, data: Dict[str, Any]) -> bool:
        """Update entity"""
        ...
    
    def delete(self, entity_id: str) -> bool:
        """Delete entity"""
        ...


class IRenewalRepository(IRepository):
    """Repository for renewal entities"""
    
    def find_by_contact(self, contact_number: str) -> List[Any]:
        """Find renewals by contact"""
        ...
    
    def find_pending(self) -> List[Any]:
        """Find pending renewals"""
        ...


class ISessionRepository(IRepository):
    """Repository for session entities"""
    
    def find_active_by_contact(self, contact_number: str) -> Optional[Any]:
        """Find active session by contact"""
        ...
    
    def find_expired_sessions(self, timeout_minutes: int) -> List[Any]:
        """Find expired sessions"""
        ...


# Notification and Queue Interfaces
class INotificationService(Protocol):
    """Interface for notification services"""
    
    def send_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification"""
        ...
    
    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send email notification"""
        ...
    
    def send_sms(self, to: str, message: str) -> Dict[str, Any]:
        """Send SMS notification"""
        ...


class IQueueService(Protocol):
    """Interface for queue services"""
    
    def enqueue(self, item: Dict[str, Any]) -> str:
        """Add item to queue"""
        ...
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """Remove item from queue"""
        ...
    
    def peek(self) -> Optional[Dict[str, Any]]:
        """Peek at next item without removing"""
        ...
    
    def size(self) -> int:
        """Get queue size"""
        ...


# Factory Interfaces
class IFlaskAppFactory(Protocol):
    """Interface for Flask application factory"""
    
    def create_app(self) -> Any:
        """Create Flask application"""
        ...

class IServiceFactory(Protocol):
    """Interface for service factories"""
    
    def create_service(self, service_type: str, **kwargs) -> IService:
        """Create service instance"""
        ...


class IWorkerFactory(Protocol):
    """Interface for worker factories"""
    
    def create_worker(self, worker_type: str, **kwargs) -> IWorker:
        """Create worker instance"""
        ...


class ITunnelService(Protocol):
    """Interface for tunnel services"""
    
    def start(self) -> None:
        """Start tunnel service"""
        ...
    
    def stop(self) -> None:
        """Stop tunnel service"""
        ...
    
    def get_public_url(self) -> str:
        """Get public URL"""
        ...


# Integration specific interfaces
class IDigisacService(Protocol):
    """Aggregated interface for Digisac services"""
    
    def send_message(self, contact_id: str, message: str) -> Dict[str, Any]:
        """Send message via Digisac"""
        ...
    
    def create_ticket(self, contact_id: str, subject: str) -> Dict[str, Any]:
        """Create ticket in Digisac"""
        ...
    
    def find_contact(self, phone: str) -> Optional[str]:
        """Find contact in Digisac"""
        ...


class IContaAzulService(Protocol):
    """Aggregated interface for Conta Azul services"""
    
    def create_sale(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create sale in Conta Azul"""
        ...
    
    def create_billing(self, billing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create billing in Conta Azul"""
        ...
    
    def find_contact(self, document: str) -> Optional[str]:
        """Find contact in Conta Azul"""
        ...


class IBitrix24Service(Protocol):
    """Aggregated interface for Bitrix24 services"""
    
    def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create lead in Bitrix24"""
        ...
    
    def update_deal(self, deal_id: str, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update deal in Bitrix24"""
        ...
    
    def fetch_company_data(self, cnpj: str) -> Dict[str, Any]:
        """Fetch company data"""
        ...


# Synchronization Interfaces
class ISyncService(Protocol):
    """Interface for synchronization services"""
    
    def sync_data(self, source: str, target: str) -> Dict[str, Any]:
        """Synchronize data between systems"""
        ...
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get synchronization status"""
        ...


class ISyncManager(Protocol):
    """Interface for synchronization managers"""
    
    def start_sync(self) -> None:
        """Start synchronization process"""
        ...
    
    def stop_sync(self) -> None:
        """Stop synchronization process"""
        ...
    
    def get_sync_progress(self) -> Dict[str, Any]:
        """Get synchronization progress"""
        ...
