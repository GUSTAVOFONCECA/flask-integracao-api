# app/core/container.py
"""
Dependency Injection Container following SOLID principles.
Implements Dependency Inversion and Single Responsibility.
"""

import logging
from typing import Any, Dict, Type, TypeVar, Callable, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

T = TypeVar("T")


class IDependencyContainer(ABC):
    """Interface for dependency injection container"""

    @abstractmethod
    def register_instance(self, interface: Type[T], instance: T) -> None:
        """Register a singleton instance"""
        pass

    @abstractmethod
    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory function"""
        pass

    @abstractmethod
    def register_type(self, interface: Type[T], implementation: Type[T]) -> None:
        """Register a type mapping"""
        pass

    @abstractmethod
    def resolve(self, interface: Type[T]) -> T:
        """Resolve an instance of the interface"""
        pass

    @abstractmethod
    def has_registration(self, interface: Type[T]) -> bool:
        """Check if interface is registered"""
        pass


class DependencyInjectionError(Exception):
    """Error in dependency injection"""

    pass


class DependencyContainer(IDependencyContainer):
    """
    Dependency injection container implementation.
    Follows Single Responsibility Principle.
    """

    def __init__(self):
        self._instances: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._types: Dict[Type, Type] = {}
        self._resolving: set = set()  # Circular dependency detection

    def register_instance(self, interface: Type[T], instance: T) -> None:
        """Register a singleton instance"""
        if not self._is_valid_interface(interface):
            raise DependencyInjectionError(f"Invalid interface: {interface}")

        self._instances[interface] = instance
        logger.debug(f"Registered instance for {interface.__name__}")

    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory function"""
        if not self._is_valid_interface(interface):
            raise DependencyInjectionError(f"Invalid interface: {interface}")

        if not callable(factory):
            raise DependencyInjectionError(f"Factory must be callable")

        self._factories[interface] = factory
        logger.debug(f"Registered factory for {interface.__name__}")

    def register_type(self, interface: Type[T], implementation: Type[T]) -> None:
        """Register a type mapping"""
        if not self._is_valid_interface(interface):
            raise DependencyInjectionError(f"Invalid interface: {interface}")

        if not self._is_valid_implementation(implementation):
            raise DependencyInjectionError(f"Invalid implementation: {implementation}")

        self._types[interface] = implementation
        logger.debug(
            f"Registered type mapping {interface.__name__} -> {implementation.__name__}"
        )

    def resolve(self, interface: Type[T]) -> T:
        """Resolve an instance of the interface"""
        if interface in self._resolving:
            raise DependencyInjectionError(
                f"Circular dependency detected for {interface.__name__}"
            )

        try:
            self._resolving.add(interface)
            return self._resolve_internal(interface)
        finally:
            self._resolving.discard(interface)

    def has_registration(self, interface: Type[T]) -> bool:
        """Check if interface is registered"""
        return (
            interface in self._instances
            or interface in self._factories
            or interface in self._types
        )

    def clear_registrations(self) -> None:
        """Clear all registrations (useful for testing)"""
        self._instances.clear()
        self._factories.clear()
        self._types.clear()
        self._resolving.clear()
        logger.debug("Cleared all registrations")

    def _resolve_internal(self, interface: Type[T]) -> T:
        """Internal resolution logic"""
        # Check for singleton instance
        if interface in self._instances:
            return self._instances[interface]

        # Check for factory
        if interface in self._factories:
            factory = self._factories[interface]
            instance = factory()
            # Cache as singleton
            self._instances[interface] = instance
            return instance

        # Check for type mapping
        if interface in self._types:
            implementation = self._types[interface]
            try:
                instance = implementation()
                # Cache as singleton
                self._instances[interface] = instance
                return instance
            except Exception as e:
                raise DependencyInjectionError(
                    f"Error creating instance of {implementation.__name__}: {e}"
                )

        raise DependencyInjectionError(
            f"No registration found for {interface.__name__}"
        )

    def _is_valid_interface(self, interface: Type) -> bool:
        """Check if interface is valid"""
        return interface is not None and isinstance(interface, type)

    def try_resolve(self, interface: Type[T]) -> Optional[T]:
        """Try to resolve an instance without raising exception"""
        try:
            return self.resolve(interface)
        except DependencyInjectionError:
            return None

    def _is_valid_implementation(self, implementation: Type) -> bool:
        """Check if implementation is valid"""
        return (
            implementation is not None
            and isinstance(implementation, type)
            and callable(implementation)
        )


# Global container instance
container = DependencyContainer()


def setup_container() -> None:
    """Setup dependency injection container"""
    from app.core.service_factory import create_service_factory
    from app.core.config_provider import EnvironmentConfigProvider
    from app.core.logging_service import LoggingService
    from app.core.interfaces import (
        IConfigProvider,
        ILogger,
        IAuthenticationService,
        IMessageService,
        ITicketService,
        IContactService,
        ISaleService,
        IBillingService,
        ICRMService,
        ITokenManager,
    )

    try:
        # Register configuration provider
        config = EnvironmentConfigProvider()
        container.register_instance(IConfigProvider, config)

        # Register logging service
        logging_service = LoggingService(config)
        container.register_instance(ILogger, logging_service)

        # Create service factory
        factory = create_service_factory()

        # Register Digisac services
        container.register_factory(
            "digisac_auth", lambda: factory.create_digisac_auth_service()
        )
        container.register_factory(
            "digisac_message", lambda: factory.create_digisac_message_service()
        )
        container.register_factory(
            "digisac_ticket", lambda: factory.create_digisac_ticket_service()
        )
        container.register_factory(
            "digisac_contact", lambda: factory.create_digisac_contact_service()
        )

        # Register Conta Azul services
        container.register_factory(
            "conta_azul_auth", lambda: factory.create_conta_azul_auth_service()
        )
        container.register_factory(
            "conta_azul_sale", lambda: factory.create_conta_azul_sale_service()
        )
        container.register_factory(
            "conta_azul_billing", lambda: factory.create_conta_azul_billing_service()
        )
        container.register_factory(
            "conta_azul_contact", lambda: factory.create_conta_azul_contact_service()
        )

        # Register Bitrix24 services
        container.register_factory(
            "bitrix24_crm", lambda: factory.create_bitrix24_crm_service()
        )

        # Register external services
        container.register_factory("cnpj_client", lambda: factory.create_cnpj_client())

        logger.info("✅ Dependency injection container configured successfully")

    except Exception as e:
        logger.error(f"❌ Error setting up dependency container: {e}")
        raise


def get_service(service_name: str) -> Any:
    """Get service from container by name"""
    try:
        return container.resolve(service_name)
    except DependencyInjectionError as e:
        logger.error(f"Error resolving service {service_name}: {e}")
        raise


def register_service(interface: Type[T], implementation: Any) -> None:
    """Register a service in the container"""
    if callable(implementation) and not isinstance(implementation, type):
        container.register_factory(interface, implementation)
    else:
        container.register_instance(interface, implementation)


# Context manager for testing
class ContainerTestContext:
    """Context manager for testing with temporary container state"""

    def __init__(self):
        self._backup_instances = {}
        self._backup_factories = {}
        self._backup_types = {}

    def __enter__(self):
        # Backup current state
        self._backup_instances = container._instances.copy()
        self._backup_factories = container._factories.copy()
        self._backup_types = container._types.copy()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore state
        container._instances = self._backup_instances
        container._factories = self._backup_factories
        container._types = self._backup_types

    def register_mock(self, interface: Type[T], mock_instance: T) -> None:
        """Register a mock for testing"""
        container.register_instance(interface, mock_instance)


def create_test_container() -> ContainerTestContext:
    """Create a test container context"""
    return ContainerTestContext()


from typing import Any, Callable, Dict

from flask import Flask

from app.core.config_provider import EnvironmentConfigProvider
from app.core.interfaces import (
    IAuthenticationService,
    IConfigProvider,
    ILogger,
    ITokenManager,
)
from app.core.logging_service import LoggingService
from app.core.interfaces import ICrmService
from app.services.bitrix24.crm_service import BitrixCRMService
from app.core.interfaces import IBillingService, ISaleService
from app.services.conta_azul.billing_service import ContaAzulBillingService
from app.services.conta_azul.sale_service import ContaAzulSaleService
from app.services.external.cnpj_client import CNPJAPIClient
from app.services.digisac.contact_service import DigisacContactService
from app.services.digisac.message_service import DigisacMessageService
from app.services.digisac.contact_service import DigisacService
from app.services.digisac.ticket_service import DigisacTicketService
from app.services.renewal_services import SessionManager
from app.services.routes import register_routes
from app.services.token_manager import TokenManager
from app.services.tunnel_service import TunnelService
from app.utils.decorators import singleton
from app.workers.session_worker import SessionWorker, create_session_worker
from app.workers.ticket_flow_worker import TicketFlowWorker, create_ticket_flow_worker
from app.workers.token_refresh_worker import (
    TokenRefreshWorker,
    create_token_refresh_worker,
)


class ServiceFactory:
    """
    Service Factory to create instances with dependencies.
    Follows Factory Pattern and Dependency Injection.
    """

    def __init__(self, flask_app: Flask):
        self.flask_app = flask_app
        self._config = None  # Initialize _config
        self._logger = None  # Initialize _logger
        self._token_manager = None  # Initialize _token_manager
        self._data_provider = None
        self._digisac_service = None
        self._session_manager = None

    @singleton
    def config(self) -> EnvironmentConfigProvider:
        """Create config provider"""
        if self._config is None:
            self._config = EnvironmentConfigProvider()
        return self._config

    @singleton
    def logger(self) -> FlaskLogger:
        """Create logger"""
        if self._logger is None:
            self._logger = FlaskLogger(self.flask_app)
        return self._logger

    @singleton
    def token_manager(self) -> ITokenManager:
        """Create token manager"""
        if self._token_manager is None:
            self._token_manager = TokenManager(self.flask_app)
        return self._token_manager

    @singleton
    def data_provider(self):
        """Create data provider"""
        if self._data_provider is None:
            from app.database.database import get_db_connection

            self._data_provider = get_db_connection
        return self._data_provider

    @singleton
    def session_manager(self):
        """Create session manager"""
        if self._session_manager is None:
            from app.services.renewal_services import create_session_manager

            self._session_manager = create_session_manager()
        return self._session_manager

    @singleton
    def digisac_service(self) -> DigisacService:
        """Create digisac service"""
        if self._digisac_service is None:
            self._digisac_service = DigisacService(self.config())
        return self._digisac_service

    def create_digisac_auth_service(self) -> IAuthenticationService:
        """Create digisac auth service"""
        return self.digisac_service()

    def create_digisac_message_service(self) -> DigisacMessageService:
        """Create digisac message service"""
        return DigisacMessageService(
            self.config(), self.digisac_service(), self.logger()
        )

    def create_digisac_ticket_service(self) -> DigisacTicketService:
        """Create digisac ticket service"""
        return DigisacTicketService(
            self.config(), self.digisac_service(), self.logger()
        )

    def create_digisac_contact_service(self) -> DigisacContactService:
        """Create digisac contact service"""
        return DigisacContactService(
            self.config(), self.digisac_service(), self.logger()
        )

    def create_conta_azul_auth_service(self) -> IAuthenticationService:
        """Create conta azul auth service"""
        from app.services.conta_azul.conta_azul_services import (
            ContaAzulService,
        )

        return ContaAzulService(self.config(), self.token_manager())

    def create_conta_azul_sale_service(self) -> ISaleService:
        """Create conta azul sale service"""
        return ContaAzulSaleService(self.config(), self.data_provider())

    def create_conta_azul_billing_service(self) -> IBillingService:
        """Create conta azul billing service"""
        return ContaAzulBillingService(self.config(), self.data_provider())

    def create_conta_azul_contact_service(self) -> DigisacContactService:
        """Create conta azul contact service"""
        return DigisacContactService(
            self.config(), self.digisac_service(), self.logger()
        )

    def create_bitrix24_crm_service(self) -> ICrmService:
        """Create bitrix24 crm service"""
        return BitrixCrmService(self.config(), self.data_provider())

    def create_cnpj_client(self) -> CnpjClient:
        """Create CNPJ client"""
        return CnpjClient(self.config())

    @singleton
    def session_worker(self) -> SessionWorker:
        """Create session worker"""
        from app.services.renewal_services import SessionManager

        session_service = SessionManager()
        return create_session_worker(
            session_service=session_service, logger=self.logger()
        )

    @singleton
    def token_refresh_worker(self) -> TokenRefreshWorker:
        """Create token refresh worker"""
        from app.services.conta_azul.conta_azul_services import get_tokens
        from app.services.digisac.digisac_services import DigisacService

        # Create a token service adapter
        class TokenServiceAdapter:
            def refresh_tokens_safely(self) -> bool:
                try:
                    # Attempt to refresh both Conta Azul and Digisac tokens
                    get_tokens()  # This should refresh Conta Azul tokens
                    return True
                except Exception:
                    return False

            def get_token_expiry_time(self) -> int:
                # Return 300 seconds (5 minutes) as default
                # This should be replaced with actual token expiry logic
                return 300

        return create_token_refresh_worker(
            token_service=TokenServiceAdapter(), logger=self.logger()
        )

    @singleton
    def ticket_flow_worker(self) -> TicketFlowWorker:
        """Create ticket flow worker"""
        from app.workers.ticket_flow_worker import (
            create_ticket_flow_worker_with_defaults,
        )

        return create_ticket_flow_worker_with_defaults(self.logger())


def create_service_factory() -> ServiceFactory:
    """Create service factory"""
    # Avoid circular import
    from app import app

    return ServiceFactory(app)


def init_services(flask_app: Flask) -> None:
    """Initialize services"""
    factory = ServiceFactory(flask_app)
    logger: ILogger = factory.logger()

    # tunnel_service = TunnelService(factory.config())
    # tunnel_service.start_tunnel()

    register_routes(flask_app)

    logger.info("✅ Services initialized successfully")


import logging

from flask import Flask

from app.core.interfaces import ILogger
from app.utils.config import config
from app.utils.util import setup_logging

_logger = logging.getLogger(__name__)


class LoggingService(ILogger):
    """
    Logging Service following Single Responsibility Principle.
    Implements logging functionalities.
    """

    def __init__(self):
        self.setup()

    def setup(self) -> None:
        """Setup logging configurations"""
        setup_logging(config.log_level)
        _logger.info("Logging service configured successfully")

    def get_logger(self, name: str) -> logging.Logger:
        """Get logger by name"""
        return logging.getLogger(name)

    def log_request(self, request) -> None:
        """Log request information"""
        _logger.info(
            "Request: %s %s %s",
            request.method,
            request.path,
            request.headers,
        )

    def log_response(self, response) -> None:
        """Log response information"""
        _logger.info("Response: %s %s", response.status_code, response.data)


class FlaskLogger(ILogger):
    """
    Flask Logger Service following Single Responsibility Principle.
    Implements logging functionalities specific to Flask.
    """

    def __init__(self, app: Flask):
        self.app = app
        self.setup()

    def setup(self) -> None:
        """Setup logging configurations"""
        if config.log_level:
            level = config.log_level.upper()
        else:
            level = "INFO"

        setup_logging(level)

        _logger.info("Flask logging service configured successfully")

        # Log application configuration at startup
        with self.app.app_context():
            for key, value in config.items():
                _logger.debug("Config: %s=%s", key, value)

    def get_logger(self, name: str) -> logging.Logger:
        """Get logger by name"""
        return logging.getLogger(name)

    def log_request(self, request) -> None:
        """Log request information"""
        _logger.info(
            "Request: %s %s %s",
            request.method,
            request.path,
            request.headers,
        )

    def log_response(self, response) -> None:
        """Log response information"""
        _logger.info("Response: %s %s", response.status_code, response.data)


"""
Worker responsible for managing session lifecycle. Follows Single Responsibility Principle.
"""

import logging
import time
from abc import ABC, abstractmethod

from app.core.interfaces import ILogger
from app.services.renewal_services import ISessionService

logger = logging.getLogger(__name__)


class IScheduledWorker(ABC):
    """Interface for scheduled workers"""

    @abstractmethod
    def start(self) -> None:
        """Start the worker"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the worker"""
        pass

    @abstractmethod
    def run(self) -> None:
        """Execute the worker's logic"""
        pass


class SessionWorker(IScheduledWorker):
    """
    Worker responsible for managing session lifecycle.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        session_service: ISessionService,
        logger: ILogger,
        interval_seconds: int = 60,
    ):
        self._session_service = session_service
        self._logger = logger.get_logger(__name__)
        self._interval_seconds = interval_seconds
        self._is_running = False

    def start(self) -> None:
        """Start the worker"""
        self._logger.info("Starting session worker...")
        self._is_running = True
        while self._is_running:
            try:
                self.run()
            except Exception as e:
                self._logger.error(f"Error running session worker: {e}")
            time.sleep(self._interval_seconds)
        self._logger.info("Session worker stopped.")

    def stop(self) -> None:
        """Stop the worker"""
        self._is_running = False
        self._logger.info("Stopping session worker...")

    def run(self) -> None:
        """Execute the worker's logic"""
        self._logger.info("Running session maintenance...")
        self._session_service.perform_session_maintenance()
        self._logger.info("Session maintenance completed.")


def create_session_worker(
    session_service: ISessionService, logger: ILogger, interval_seconds: int = 60
) -> SessionWorker:
    """Create session worker"""
    return SessionWorker(session_service, logger, interval_seconds)


"""
Worker responsible for refreshing tokens. Follows Single Responsibility Principle.
"""

import logging
import time
from abc import ABC, abstractmethod

from app.core.interfaces import ILogger


class ITokenRefreshService(ABC):
    """Interface for token refresh service"""

    @abstractmethod
    def refresh_tokens_safely(self) -> bool:
        """Refresh tokens safely"""
        pass

    @abstractmethod
    def get_token_expiry_time(self) -> int:
        """Get token expiry time"""
        pass


class TokenRefreshWorker(IScheduledWorker):
    """
    Worker responsible for refreshing tokens.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        token_service: ITokenRefreshService,
        logger: ILogger,
        interval_seconds: int = 600,
    ):
        self._token_service = token_service
        self._logger = logger.get_logger(__name__)
        self._interval_seconds = interval_seconds
        self._is_running = False

    def start(self) -> None:
        """Start the worker"""
        self._logger.info("Starting token refresh worker...")
        self._is_running = True
        while self._is_running:
            try:
                self.run()
            except Exception as e:
                self._logger.error(f"Error running token refresh worker: {e}")
            time.sleep(self._interval_seconds)
        self._logger.info("Token refresh worker stopped.")

    def stop(self) -> None:
        """Stop the worker"""
        self._is_running = False
        self._logger.info("Stopping token refresh worker...")

    def run(self) -> None:
        """Execute the worker's logic"""
        self._logger.info("Checking and refreshing tokens...")
        try:
            self._token_service.refresh_tokens_safely()
        except Exception as e:
            self._logger.error(f"❌ Token refresh failed: {e}")
        self._logger.info("Token refresh check completed.")


def create_token_refresh_worker(
    token_service: ITokenRefreshService, logger: ILogger, interval_seconds: int = 600
) -> TokenRefreshWorker:
    """Create token refresh worker"""
    return TokenRefreshWorker(token_service, logger, interval_seconds)


"""
Worker responsible for handling ticket flow. Follows Single Responsibility Principle.
"""

import logging
import time
from abc import ABC, abstractmethod

from app.core.interfaces import ILogger

logger = logging.getLogger(__name__)


class ITicketFlowService(ABC):
    """Interface for ticket flow service"""

    @abstractmethod
    def handle_ticket_flow(self) -> None:
        """Handle ticket flow"""
        pass


class TicketFlowWorker(IScheduledWorker):
    """
    Worker responsible for handling ticket flow.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        ticket_flow_service: ITicketFlowService,
        logger: ILogger,
        interval_seconds: int = 3600,
    ):
        self._ticket_flow_service = ticket_flow_service
        self._logger = logger.get_logger(__name__)
        self._interval_seconds = interval_seconds
        self._is_running = False

    def start(self) -> None:
        """Start the worker"""
        self._logger.info("Starting ticket flow worker...")
        self._is_running = True
        while self._is_running:
            try:
                self.run()
            except Exception as e:
                self._logger.error(f"Error running ticket flow worker: {e}")
            time.sleep(self._interval_seconds)
        self._logger.info("Ticket flow worker stopped.")

    def stop(self) -> None:
        """Stop the worker"""
        self._is_running = False
        self._logger.info("Stopping ticket flow worker...")

    def run(self) -> None:
        """Execute the worker's logic"""
        self._logger.info("Handling ticket flow...")
        self._ticket_flow_service.handle_ticket_flow()
        self._logger.info("Ticket flow handling completed.")


def create_ticket_flow_worker(
    ticket_flow_service: ITicketFlowService,
    logger: ILogger,
    interval_seconds: int = 3600,
) -> TicketFlowWorker:
    """Create ticket flow worker"""
    return TicketFlowWorker(ticket_flow_service, logger, interval_seconds)


def create_ticket_flow_worker_with_defaults(logger: ILogger) -> TicketFlowWorker:
    """Create ticket flow worker with default settings"""
    # Here you would inject your actual TicketFlowService
    # from app.services.ticket_flow_service import TicketFlowService
    # ticket_flow_service = TicketFlowService()

    # For now, we'll use a dummy service
    class DummyTicketFlowService(ITicketFlowService):
        def handle_ticket_flow(self) -> None:
            logger.get_logger(__name__).info("Dummy ticket flow handling...")

    dummy_ticket_flow_service = DummyTicketFlowService()
    return create_ticket_flow_worker(dummy_ticket_flow_service, logger)
