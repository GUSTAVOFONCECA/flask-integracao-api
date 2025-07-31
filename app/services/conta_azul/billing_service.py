# app/services/conta_azul/billing_service.py
"""
Conta Azul billing service following Single Responsibility and Interface Segregation Principles.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests

from app.core.interfaces import IBillingService, ITokenManager
from app.core.config_provider import ServiceConfiguration
from app.utils.utils import debug


logger = logging.getLogger(__name__)


class ContaAzulBillingService(IBillingService):
    """Billing service for Conta Azul following SRP and ISP"""

    def __init__(self, token_manager: ITokenManager, bank_account_uuid: str):
        self.token_manager = token_manager
        self.bank_account_uuid = bank_account_uuid
        self.base_url = ServiceConfiguration.CONTA_AZUL_API_BASE_URL

    @debug
    def generate_billing(
        self, sale_id: str, due_date: datetime = None
    ) -> Dict[str, Any]:
        """Generate billing for sale"""
        # Get financial event ID and parcel ID from sale
        financial_event_info = self._get_financial_event_info(sale_id)
        parcel_id = financial_event_info["parcel_id"]

        if due_date is None:
            due_date = datetime.now()

        url = f"{self.base_url}/v1/financeiro/eventos-financeiros/contas-a-receber/gerar-cobranca"
        headers = self.token_manager.get_auth_headers()

        payload = {
            "conta_bancaria": str(self.bank_account_uuid),
            "descricao_fatura": "Emissão de Certificado Digital",
            "id_parcela": parcel_id,
            "data_vencimento": due_date.strftime("%Y-%m-%d"),
            "tipo": "BOLETO",
            "atributos": {},
        }

        logger.debug(f"POST {url}")
        logger.debug(f"Payload: {payload}")

        response = requests.post(url, json=payload, headers=headers, timeout=60)

        if response.status_code >= 400:
            logger.error(f"Detailed error: {response.text}")

        response.raise_for_status()

        logger.info(f"HTTP Response {response.status_code}")
        return response.json()

    @debug
    def get_billing_url(self, sale_id: str) -> Optional[str]:
        """Get billing URL for sale"""
        financial_event_info = self._get_financial_event_info(sale_id)
        financial_event_id = financial_event_info["financial_event_id"]

        parcels = self._get_financial_event_parcels(financial_event_id)

        for parcel in parcels:
            billing_requests = parcel.get("solicitacoes_cobrancas", [])
            for request in billing_requests:
                if request.get("tipo_solicitacao_cobranca") == "BOLETO_REGISTRADO":
                    url = request.get("url")
                    if url:
                        return url

        logger.warning(f"Billing URL not found for sale: {sale_id}")
        return None

    def _get_financial_event_info(self, sale_id: str) -> Dict[str, str]:
        """Get financial event information from sale"""
        url = f"{self.base_url}/v1/venda/{sale_id}"
        headers = self.token_manager.get_auth_headers()

        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            sale_details = response.json()

            financial_event = sale_details.get("evento_financeiro") or {}
            financial_event_id = financial_event.get("id")

            if not financial_event_id:
                raise ValueError("Financial event ID not found")

            # Get first parcel ID
            parcels = self._get_financial_event_parcels(financial_event_id)
            if not parcels:
                raise ValueError("No parcels found for financial event")

            parcel_id = parcels[0].get("id")
            if not parcel_id:
                raise ValueError("Parcel ID not found")

            return {"financial_event_id": financial_event_id, "parcel_id": parcel_id}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting financial event info: {str(e)}")
            raise

    @debug
    def _get_financial_event_parcels(
        self, financial_event_id: str
    ) -> List[Dict[str, Any]]:
        """Get parcels for financial event"""
        url = f"{self.base_url}/v1/financeiro/eventos-financeiros/{financial_event_id}/parcelas"
        headers = self.token_manager.get_auth_headers()

        try:
            logger.debug(f"GET {url}")
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            logger.debug(f"Response: {response.json()}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting financial event parcels: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
