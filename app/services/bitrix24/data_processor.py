# app/services/bitrix24/data_processor.py
"""
Bitrix24 data processor following Single Responsibility Principle.
"""

import re
import logging
from typing import Dict, Any

from app.core.interfaces import IDataProcessor


logger = logging.getLogger(__name__)


class BitrixCNPJDataProcessor(IDataProcessor):
    """CNPJ data processor for Bitrix24 following SRP"""

    def process_cnpj_data(
        self, cnpj_data: Dict[str, Any], company_id: str
    ) -> Dict[str, Any]:
        """Process CNPJ data for Bitrix24 CRM format"""
        company = cnpj_data.get("estabelecimento", {})

        # Process address
        endereco = ", ".join(
            filter(
                None,
                [
                    f"{self._safe_get(company, 'tipo_logradouro')} {self._safe_get(company, 'logradouro')}",
                    (
                        f"N° {self._safe_get(company, 'numero')}"
                        if self._safe_get(company, "numero")
                        else ""
                    ),
                    (
                        re.sub(
                            r"\s{2,}", " ", self._safe_get(company, "complemento")
                        ).strip()
                        if self._safe_get(company, "complemento")
                        else ""
                    ),
                ],
            )
        ).strip(", ")

        # Format CNPJ
        cnpj_formatado = re.sub(
            r"(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})",
            r"\1.\2.\3/\4-\5",
            self._safe_get(company, "cnpj"),
        )

        processed_data = {
            "id": str(company_id),
            "fields": {
                "UF_CRM_1708977581412": cnpj_formatado,
                "TITLE": self._safe_get(cnpj_data, "razao_social"),
                "UF_CRM_1709838249844": self._safe_get(company, "nome_fantasia"),
                "ADDRESS": endereco,
                "ADDRESS_REGION": self._safe_get(company, "bairro"),
                "ADDRESS_CITY": company.get("cidade", {}).get("nome", ""),
                "ADDRESS_PROVINCE": company.get("estado", {}).get("nome", ""),
                "ADDRESS_POSTAL_CODE": re.sub(
                    r"(\d{5})(\d{3})", r"\1-\2", self._safe_get(company, "cep")
                ),
                "UF_CRM_1710938520402": next(
                    (
                        self._safe_get(insc, "inscricao_estadual")
                        for insc in company.get("inscricoes_estaduais", [])[:1]
                    ),
                    "Não Contribuinte",
                ),
                "UF_CRM_1720974662288": "Y",
            },
            "params": {"REGISTER_SONET_EVENT": "N"},
        }

        logger.debug("Processed CNPJ data: %s", processed_data)
        return processed_data

    def _safe_get(self, data: Dict[str, Any], key: str, default: str = "") -> str:
        """Safely get value from dictionary"""
        value = data.get(key)
        return str(value).strip() if value is not None else default
