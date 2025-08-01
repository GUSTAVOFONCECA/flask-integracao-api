# app/services/external/cnpj_client.py
"""
External CNPJ API client following Dependency Inversion Principle.
"""

import re
import logging
from typing import Dict, Any, Optional
import requests

from app.core.interfaces import IExternalAPIClient


logger = logging.getLogger(__name__)


class CNPJAPIClient(IExternalAPIClient):
    """CNPJ API client following DIP"""

    def __init__(self, base_url: str = "https://publica.cnpj.ws"):
        self.base_url = base_url

    def get_cnpj_data(self, cnpj: str) -> Optional[Dict[str, Any]]:
        """Get CNPJ data from public API"""
        cnpj_clean = re.sub(r"[\.\/-]", "", str(cnpj))
        url = f"{self.base_url}/cnpj/{cnpj_clean}"

        return self.make_request("GET", url)

    def make_request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to external API"""
        try:
            response = requests.request(method, url, timeout=60, **kwargs)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                logger.error("API error: %s", data["error"])
                return None

            logger.info("CNPJ data obtained successfully")
            logger.debug("Payload: %s", data)
            return data

        except requests.exceptions.RequestException as e:
            logger.error("Request failed: %s", str(e))
            return None
