# app/services/conta_azul/sale_service.py
"""
Conta Azul sale service following Single Responsibility and Interface Segregation Principles.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import requests

from app.core.interfaces import ISaleService, ITokenManager
from app.core.config_provider import ServiceConfiguration
from app.utils.utils import debug


logger = logging.getLogger(__name__)


class ContaAzulSaleService(ISaleService):
    """Sale service for Conta Azul following SRP and ISP"""

    def __init__(self, token_manager: ITokenManager, bank_account_uuid: str):
        self.token_manager = token_manager
        self.bank_account_uuid = bank_account_uuid
        self.base_url = ServiceConfiguration.CONTA_AZUL_API_BASE_URL

    @debug
    def create_sale(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sale"""
        payload = self._build_sale_payload(sale_data)

        url = f"{self.base_url}/v1/venda"
        headers = self.token_manager.get_auth_headers()

        try:
            logger.debug(f"POST {url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Payload: {payload}")

            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            logger.info(f"HTTP Response {response.status_code}")
            logger.debug(f"Content: {response.text}")

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise

    @debug
    def get_sale_details(self, sale_id: str) -> Dict[str, Any]:
        """Get sale details by ID"""
        url = f"{self.base_url}/v1/venda/{sale_id}"
        headers = self.token_manager.get_auth_headers()

        try:
            logger.debug(f"GET {url}")
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            logger.debug(f"Content: {response.content}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting sale details: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise

    @debug
    def get_sale_pdf(self, sale_id: str) -> bytes:
        """Get sale PDF"""
        url = f"{self.base_url}/v1/venda/{sale_id}/imprimir"
        headers = self.token_manager.get_auth_headers()

        try:
            logger.debug(f"GET {url}")
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting sale PDF: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise

    def build_certification_sale_data(
        self, client_id: str, deal_type: str
    ) -> Dict[str, Any]:
        """Build sale data for digital certification"""
        params = self._get_certification_params(deal_type)

        return {
            "client_id": client_id,
            "service_id": params["service_id"],
            "price": params["price"],
            "item_description": params["description"],
            "sale_date": datetime.now(),
            "due_date": datetime.now() + timedelta(days=5),
        }

    def _build_sale_payload(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build sale payload for API"""
        # Generate sequential number based on timestamp
        numero_venda = int(datetime.now().timestamp())

        return {
            "id_cliente": sale_data["client_id"],
            "numero": numero_venda,
            "situacao": "APROVADO",
            "data_venda": sale_data["sale_date"].strftime("%Y-%m-%d"),
            "itens": [
                {
                    "descricao": sale_data["item_description"],
                    "quantidade": 1,
                    "valor": float(sale_data["price"]),
                    "id": sale_data["service_id"],
                }
            ],
            "condicao_pagamento": {
                "tipo_pagamento": "BOLETO_BANCARIO",
                "id_conta_financeira": self.bank_account_uuid,
                "opcao_condicao_pagamento": "1x",
                "parcelas": [
                    {
                        "data_vencimento": sale_data["due_date"].strftime("%Y-%m-%d"),
                        "valor": float(sale_data["price"]),
                        "descricao": "Parcela única",
                    }
                ],
            },
        }

    def _get_certification_params(self, deal_type: str) -> Dict[str, Any]:
        """Get certification parameters by deal type"""
        if deal_type == "Pessoa jurídica":
            return {
                "service_id": ServiceConfiguration.CERT_PJ_SERVICE_ID,
                "description": "CERTIFICADO DIGITAL PJ",
                "price": ServiceConfiguration.CERT_PJ_PRICE,
            }
        elif deal_type in ["Pessoa física - CPF", "Pessoa física - CEI"]:
            return {
                "service_id": ServiceConfiguration.CERT_PF_SERVICE_ID,
                "description": "CERTIFICADO DIGITAL PF",
                "price": ServiceConfiguration.CERT_PF_PRICE,
            }
        else:
            raise ValueError(f"Invalid deal type: {deal_type}")
