# app/core/service_factory.py
"""
Service factory implementing Dependency Inversion Principle.
"""

import os
from pathlib import Path

from app.core.interfaces import (
    IConfigProvider,
    IAuthenticationService,
    ITokenManager,
    IMessageService,
    ITicketService,
    IContactService,
    ISaleService,
    IBillingService,
)
from app.core.config_provider import EnvironmentConfigProvider

# Digisac services
from app.services.digisac.authentication_service import (
    DigisacAuthenticationService,
    DigisacTokenManager,
)
from app.services.digisac.message_service import DigisacMessageService
from app.services.digisac.ticket_service import DigisacTicketService
from app.services.digisac.contact_service import DigisacContactService

# Conta Azul services
from app.services.conta_azul.authentication_service import (
    ContaAzulAuthenticationService,
    ContaAzulTokenManager,
)
from app.services.conta_azul.sale_service import ContaAzulSaleService
from app.services.conta_azul.billing_service import ContaAzulBillingService
from app.services.conta_azul.contact_service import ContaAzulContactService


class ServiceFactory:
    """Factory for creating service instances following DIP"""

    def __init__(self, config: IConfigProvider):
        self.config = config
        self._digisac_token_manager = None
        self._conta_azul_token_manager = None

    # Digisac Services

    def create_digisac_token_manager(self) -> ITokenManager:
        """Create Digisac token manager"""
        if self._digisac_token_manager is None:
            tokens_file = os.path.join(
                "app", "database", "digisac", "digisac_tokens.json"
            )
            self._digisac_token_manager = DigisacTokenManager(tokens_file)
        return self._digisac_token_manager

    def create_digisac_auth_service(self) -> IAuthenticationService:
        """Create Digisac authentication service"""
        token_manager = self.create_digisac_token_manager()
        return DigisacAuthenticationService(self.config, token_manager)

    def create_digisac_message_service(self) -> IMessageService:
        """Create Digisac message service"""
        token_manager = self.create_digisac_token_manager()
        return DigisacMessageService(token_manager)

    def create_digisac_ticket_service(self) -> ITicketService:
        """Create Digisac ticket service"""
        token_manager = self.create_digisac_token_manager()
        return DigisacTicketService(token_manager)

    def create_digisac_contact_service(self) -> IContactService:
        """Create Digisac contact service"""
        contacts_file = os.path.join(
            "app", "database", "digisac", "digisac_contacts.json"
        )
        return DigisacContactService(contacts_file)

    # Conta Azul Services

    def create_conta_azul_token_manager(self) -> ITokenManager:
        """Create Conta Azul token manager"""
        if self._conta_azul_token_manager is None:
            tokens_file = os.path.join(
                "app", "database", "conta_azul", "conta_azul_tokens.json"
            )
            self._conta_azul_token_manager = ContaAzulTokenManager(tokens_file)
        return self._conta_azul_token_manager

    def create_conta_azul_auth_service(self) -> IAuthenticationService:
        """Create Conta Azul authentication service"""
        token_manager = self.create_conta_azul_token_manager()
        return ContaAzulAuthenticationService(self.config, token_manager)

    def create_conta_azul_sale_service(self) -> ISaleService:
        """Create Conta Azul sale service"""
        token_manager = self.create_conta_azul_token_manager()
        bank_account_uuid = self.config.get("CONTA_AZUL_CONTA_BANCARIA_UUID")
        return ContaAzulSaleService(token_manager, bank_account_uuid)

    def create_conta_azul_billing_service(self) -> IBillingService:
        """Create Conta Azul billing service"""
        token_manager = self.create_conta_azul_token_manager()
        bank_account_uuid = self.config.get("CONTA_AZUL_CONTA_BANCARIA_UUID")
        return ContaAzulBillingService(token_manager, bank_account_uuid)

    def create_conta_azul_contact_service(self) -> IContactService:
        """Create Conta Azul contact service"""
        persons_file = os.path.join("app", "database", "conta_azul", "person.json")
        return ContaAzulContactService(persons_file)

    def create_cnpj_client(self):
        """Create CNPJ client service"""
        from app.services.external.cnpj_client import CNPJAPIClient

        return CNPJAPIClient()

    def create_bitrix24_crm_service(self):
        """Create Bitrix24 CRM service"""
        from app.services.bitrix24.crm_service import BitrixCRMService

        return BitrixCRMService(self.config)


# Global factory instance
def create_service_factory() -> ServiceFactory:
    """Create service factory with environment configuration"""
    config = EnvironmentConfigProvider()
    config.validate()
    return ServiceFactory(config)
