# app/core/service_factory.py
"""
Service Factory following SOLID principles.
Implements Factory Pattern with Dependency Injection.
"""

from typing import Any, Protocol
from flask import Flask
import logging

from app.core.interfaces import (
    IAuthenticationService,
    IConfigProvider,
    ILogger,
    ITokenManager,
    IBillingService,
    ISaleService,
    ICRMService,
    IMessageService,
    ITicketService,
    IContactService,
)

logger = logging.getLogger(__name__)


class IServiceFactory(Protocol):
    """Interface for service factories - ISP compliant"""

    def create_digisac_auth_service(self) -> IAuthenticationService:
        """Create digisac auth service"""
        ...

    def create_conta_azul_auth_service(self) -> IAuthenticationService:
        """Create conta azul auth service"""
        ...

    def create_message_service(self) -> IMessageService:
        """Create message service"""
        ...


class AbstractServiceFactory:
    """
    Abstract service factory following SRP and DIP.
    Depends on abstractions, not concretions.
    """

    def __init__(self, config_provider: IConfigProvider, logger: ILogger):
        self._config = config_provider
        self._logger = logger

    def get_config(self) -> IConfigProvider:
        """Get configuration provider"""
        return self._config

    def get_logger(self) -> ILogger:
        """Get logger"""
        return self._logger


class DigisacServiceFactory(AbstractServiceFactory):
    """
    Factory for Digisac services - SRP compliant.
    Only responsible for creating Digisac-related services.
    """

    def __init__(
        self,
        config_provider: IConfigProvider,
        logger: ILogger,
        token_manager: ITokenManager,
    ):
        super().__init__(config_provider, logger)
        self._token_manager = token_manager

    def create_auth_service(self) -> IAuthenticationService:
        """Create Digisac auth service"""
        from app.services.digisac.authentication_service import (
            DigisacAuthenticationService,
        )

        return DigisacAuthenticationService(self._config, self._token_manager)

    def create_message_service(self) -> IMessageService:
        """Create Digisac message service"""
        from app.services.digisac.message_service import DigisacMessageService

        auth_service = self.create_auth_service()
        return DigisacMessageService(self._token_manager)

    def create_ticket_service(self) -> ITicketService:
        """Create Digisac ticket service"""
        from app.services.digisac.ticket_service import DigisacTicketService

        auth_service = self.create_auth_service()
        return DigisacTicketService(self._token_manager)

    def create_contact_service(self) -> IContactService:
        """Create Digisac contact service"""
        from app.services.digisac.contact_service import DigisacContactService

        auth_service = self.create_auth_service()
        return DigisacContactService(self._token_manager)


class ContaAzulServiceFactory(AbstractServiceFactory):
    """
    Factory for Conta Azul services - SRP compliant.
    Only responsible for creating Conta Azul-related services.
    """

    def __init__(
        self,
        config_provider: IConfigProvider,
        logger: ILogger,
        token_manager: ITokenManager,
    ):
        super().__init__(config_provider, logger)
        self._token_manager = token_manager

    def create_auth_service(self) -> IAuthenticationService:
        """Create Conta Azul auth service"""
        from app.services.conta_azul.authentication_service import (
            ContaAzulAuthenticationService,
        )

        return ContaAzulAuthenticationService(self._config, self._token_manager)

    def create_sale_service(self) -> ISaleService:
        """Create Conta Azul sale service"""
        from app.services.conta_azul.sale_service import ContaAzulSaleService

        return ContaAzulSaleService(self._config)

    def create_billing_service(self) -> IBillingService:
        """Create Conta Azul billing service"""
        from app.services.conta_azul.billing_service import ContaAzulBillingService

        return ContaAzulBillingService(self._config)


class Bitrix24ServiceFactory(AbstractServiceFactory):
    """
    Factory for Bitrix24 services - SRP compliant.
    Only responsible for creating Bitrix24-related services.
    """

    def create_crm_service(self) -> ICRMService:
        """Create Bitrix24 CRM service"""
        from app.services.bitrix24.crm_service import BitrixCRMService

        return BitrixCRMService(self._config)


class ExternalServiceFactory(AbstractServiceFactory):
    """
    Factory for external services - SRP compliant.
    Only responsible for creating external API services.
    """

    def create_cnpj_client(self):
        """Create CNPJ client"""
        from app.services.external.cnpj_client import CNPJAPIClient

        return CNPJAPIClient(self._config)


class CompositeServiceFactory(IServiceFactory):
    """
    Composite service factory - follows Facade pattern.
    Provides unified interface to all service factories.
    """

    def __init__(
        self,
        config_provider: IConfigProvider,
        logger: ILogger,
        token_manager: ITokenManager,
    ):
        self._digisac_factory = DigisacServiceFactory(config_provider, logger, token_manager)
        self._conta_azul_factory = ContaAzulServiceFactory(
            config_provider, logger, token_manager
        )
        self._bitrix24_factory = Bitrix24ServiceFactory(config_provider, logger)
        self._external_factory = ExternalServiceFactory(config_provider, logger)

    def create_digisac_auth_service(self) -> IAuthenticationService:
        """Create digisac auth service"""
        return self._digisac_factory.create_auth_service()

    def create_conta_azul_auth_service(self) -> IAuthenticationService:
        """Create conta azul auth service"""
        return self._conta_azul_factory.create_auth_service()

    def create_message_service(self) -> IMessageService:
        """Create message service"""
        return self._digisac_factory.create_message_service()

    def create_ticket_service(self) -> ITicketService:
        """Create ticket service"""
        return self._digisac_factory.create_ticket_service()

    def create_contact_service(self) -> IContactService:
        """Create contact service"""
        return self._digisac_factory.create_contact_service()

    def create_sale_service(self) -> ISaleService:
        """Create sale service"""
        return self._conta_azul_factory.create_sale_service()

    def create_billing_service(self) -> IBillingService:
        """Create billing service"""
        return self._conta_azul_factory.create_billing_service()

    def create_crm_service(self) -> ICRMService:
        """Create CRM service"""
        return self._bitrix24_factory.create_crm_service()

    def create_cnpj_client(self):
        """Create CNPJ client"""
        return self._external_factory.create_cnpj_client()


def create_service_factory() -> CompositeServiceFactory:
    """Create service factory - follows DIP"""
    from app.core.container import container
    from app.core.interfaces import IConfigProvider, ILogger, ITokenManager

    # Resolve dependencies from container
    config_provider = container.resolve(IConfigProvider)
    logger_service = container.resolve(ILogger)

    # Create token manager
    from app.services.token_manager import TokenManager

    token_manager = TokenManager()

    return CompositeServiceFactory(config_provider, logger_service, token_manager)


def init_services(flask_app: Flask) -> None:
    """Initialize services - follows SRP"""
    try:
        from app.core.container import setup_container
        from app.services.routes import register_routes

        # Setup dependency injection
        setup_container()

        # Register routes
        register_routes(flask_app)

        logger.info("✅ Services initialized successfully")
    except Exception as e:
        logger.error(f"❌ Error initializing services: {e}")
        raise
