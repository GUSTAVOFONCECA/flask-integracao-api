# app/services/certification_facade.py
"""
Certification facade following Facade Pattern and SOLID principles.
"""

import logging
import time
from typing import Dict, Any, Optional

from app.core.interfaces import (
    IMessageService,
    ITicketService,
    IContactService,
    ISaleService,
    IBillingService,
    ICRMService,
)
from app.core.config_provider import ServiceConfiguration
from app.services.renewal_services import get_pending, update_pending_status
from app.utils.utils import debug


logger = logging.getLogger(__name__)


class CertificationDigitalFacade:
    """
    Facade for digital certification operations following SOLID principles.
    Coordinates multiple services to handle certification workflow.
    """

    def __init__(
        self,
        digisac_message_service: IMessageService,
        digisac_ticket_service: ITicketService,
        digisac_contact_service: IContactService,
        conta_azul_sale_service: ISaleService,
        conta_azul_billing_service: IBillingService,
        conta_azul_contact_service: IContactService,
        crm_service: ICRMService,
        user_id: str,
    ):
        self.digisac_message = digisac_message_service
        self.digisac_ticket = digisac_ticket_service
        self.digisac_contact = digisac_contact_service
        self.conta_azul_sale = conta_azul_sale_service
        self.conta_azul_billing = conta_azul_billing_service
        self.conta_azul_contact = conta_azul_contact_service
        self.crm_service = crm_service
        self.user_id = user_id

    @debug
    def send_renewal_notification(
        self,
        contact_number: str,
        contact_name: str,
        company_name: str,
        days_to_expire: int,
        deal_type: str,
    ) -> Dict[str, Any]:
        """Send renewal notification message"""
        contact_id = self.digisac_contact.find_contact_by_phone(contact_number)
        if not contact_id:
            raise ValueError(f"Contact not found for number: {contact_number}")

        message_text = self._build_certification_message_text(
            contact_name, company_name, days_to_expire, deal_type
        )

        return self.digisac_message.send_text_message(
            contact_id=contact_id,
            message=message_text,
            department_id=ServiceConfiguration.CERT_DEPT_ID,
            user_id=self.user_id,
        )

    @debug
    def transfer_to_certification(
        self, contact_number: str, to_queue: bool = False
    ) -> Dict[str, Any]:
        """Transfer ticket to certification department"""
        contact_id = self.digisac_contact.find_contact_by_phone(contact_number)
        if not contact_id:
            raise ValueError(f"Contact not found for number: {contact_number}")

        user_id = None if to_queue else self.user_id

        return self.digisac_ticket.transfer_ticket(
            contact_id=contact_id,
            department_id=ServiceConfiguration.CERT_DEPT_ID,
            comments="Chamado aberto via automação para renovação de certificado.",
            user_id=user_id,
        )

    @debug
    def send_proposal(
        self, contact_number: str, company_name: str, spa_id: int
    ) -> Dict[str, Any]:
        """Send commercial proposal for certification"""
        contact_id = self.digisac_contact.find_contact_by_phone(contact_number)
        if not contact_id:
            raise ValueError(f"Contact not found for number: {contact_number}")

        # Send initial message
        init_message = (
            "*Bot*\nSua proposta está sendo gerada e será enviada em instantes."
        )
        self.digisac_message.send_text_message(
            contact_id=contact_id,
            message=init_message,
            department_id=ServiceConfiguration.CERT_DEPT_ID,
            user_id=self.user_id,
        )

        # Start Bitrix workflow to generate proposal
        doc_id = [
            "crm",
            "Bitrix\\Crm\\Integration\\BizProc\\Document\\Dynamic",
            f"DYNAMIC_137_{spa_id}",
        ]
        self.crm_service.start_workflow(template_id=556, document_id=doc_id)
        time.sleep(45)

        # Get proposal PDF from CRM
        pdf_content = self._get_proposal_pdf_from_crm(spa_id)

        # Send PDF
        filename = "Proposta_certificado_digital_-_Logic_Assessoria_Empresarial.pdf"
        self.digisac_message.send_file_message(
            contact_id=contact_id,
            file_content=pdf_content,
            filename=filename,
            message="Proposta",
            user_id=self.user_id,
        )

        # Send final message
        final_message = (
            "*Bot*\n"
            "Olá! Segue a proposta comercial para renovação do "
            f"certificado digital da empresa *{company_name}*.\n"
            "Qualquer dúvida, estamos à disposição."
        )
        return self.digisac_message.send_text_message(
            contact_id=contact_id,
            message=final_message,
            department_id=ServiceConfiguration.CERT_DEPT_ID,
            user_id=self.user_id,
        )

    @debug
    def create_sale_and_billing(
        self, contact_number: str, document: str, deal_type: str
    ) -> Dict[str, Any]:
        """Create sale and generate billing for certification"""
        # Find client in Conta Azul
        client_uuid = self.conta_azul_contact.find_contact_by_document(document)
        if not client_uuid:
            raise ValueError(f"Client not found for document: {document}")

        # Create sale
        sale_data = self.conta_azul_sale.build_certification_sale_data(
            client_uuid, deal_type
        )
        sale_result = self.conta_azul_sale.create_sale(sale_data)

        # Update pending status
        update_pending_status(
            contact_number, status="sale_created", sale_id=sale_result.get("id")
        )

        # Generate billing
        sale_id = sale_result.get("id")
        billing_result = self.conta_azul_billing.generate_billing(sale_id)

        return {"sale": sale_result, "billing": billing_result}

    @debug
    def send_billing_notification(
        self, contact_number: str, company_name: str, deal_id: int
    ) -> Dict[str, Any]:
        """Send billing notification with PDF"""
        contact_id = self.digisac_contact.find_contact_by_phone(contact_number)
        if not contact_id:
            raise ValueError(f"Contact not found for number: {contact_number}")

        # Get billing URL from CRM
        billing_url = self._get_billing_url_from_crm(deal_id)

        # Download billing PDF
        import requests

        response = requests.get(billing_url, timeout=60)
        response.raise_for_status()
        pdf_content = response.content

        # Send text message
        message = (
            "*Bot*\n"
            "Segue boleto para pagamento referente à emissão "
            f"de certificado digital da empresa *{company_name}*."
        )
        self.digisac_message.send_text_message(
            contact_id=contact_id,
            message=message,
            department_id=ServiceConfiguration.CERT_DEPT_ID,
            user_id=self.user_id,
        )

        # Send PDF
        filename = f"Cobranca_{company_name}.pdf"
        return self.digisac_message.send_file_message(
            contact_id=contact_id,
            file_content=pdf_content,
            filename=filename,
            message="Cobrança",
            user_id=self.user_id,
        )

    def has_open_ticket_in_other_department(self, contact_number: str) -> bool:
        """Check if contact has open ticket in other department"""
        contact_id = self.digisac_contact.find_contact_by_phone(contact_number)
        if not contact_id:
            return False

        return self.digisac_ticket.has_open_ticket(
            contact_id, exclude_department_id=ServiceConfiguration.CERT_DEPT_ID
        )

    def _build_certification_message_text(
        self, contact_name: str, company_name: str, days_to_expire: int, deal_type: str
    ) -> str:
        """Build certification message text based on deal type"""
        days = abs(days_to_expire)
        validade_msg = (
            f"*IRÁ EXPIRAR EM {days} DIAS.*"
            if days_to_expire >= 0
            else f"*EXPIROU HÁ {days} DIAS.*"
        )

        if deal_type == "Pessoa jurídica":
            price = "R$ 185,00"
            total = "R$ 186,99"
            type_msg = "o certificado da empresa"
        else:
            price = "R$ 130,00"
            total = "R$ 131,99"
            type_msg = "o certificado de Pessoa Fisica"

        return (
            "*Bot*\n"
            f"Olá {contact_name}, {type_msg} *{company_name}* {validade_msg}\n"
            f"O valor para emissão do certificado é de *{price}.*\n"
            "O valor da taxa de boleto é de *R$ 1,99.*\n"
            f"*Total da cobrança: {total}*\n\n"
            "Escolha uma das opções abaixo, digitando *exatamente* a palavra:\n\n"
            "✅ Digite: *RENOVAR* → Iniciar o processo de emissão\n"
            "ℹ️ Digite: *INFO* → Falar com um atendente para mais informações\n"
            "❌ Digite: *RECUSAR* → Não deseja renovar o certificado no momento"
        )

    def _get_proposal_pdf_from_crm(self, spa_id: int) -> bytes:
        """Get proposal PDF from CRM"""
        max_retries = 6
        retries = 0

        while retries < max_retries:
            crm_item = self.crm_service.get_item(entity_type_id=137, item_id=spa_id)
            doc_info = (
                crm_item.get("result", {}).get("item", {}).get("UF_CRM_18_1752245366")
            )

            if doc_info and isinstance(doc_info, dict) and "urlMachine" in doc_info:
                import requests

                response = requests.get(doc_info["urlMachine"], timeout=60)
                response.raise_for_status()
                return response.content

            retries += 1
            if retries >= max_retries:
                raise Exception("Max retries exceeded while getting proposal PDF")

            logger.warning(
                f"Proposal not available yet (attempt {retries}), waiting 30s"
            )
            time.sleep(30)

    def _get_billing_url_from_crm(self, deal_id: int) -> str:
        """Get billing URL from CRM"""
        max_retries = 6
        retries = 0

        while retries < max_retries:
            deal = self.crm_service.get_deal(deal_id)
            doc_url = deal.get("result", {}).get("UF_CRM_1751478607")

            if isinstance(doc_url, str) and doc_url.startswith(
                "https://public.contaazul.com"
            ):
                return doc_url

            retries += 1
            if retries >= max_retries:
                raise Exception("Max retries exceeded while getting billing URL")

            logger.warning(
                f"Billing URL not found for Deal ID {deal_id} (attempt {retries})"
            )
            time.sleep(30)
