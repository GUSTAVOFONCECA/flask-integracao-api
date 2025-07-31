# app/services/digisac/message_service.py
"""
Digisac message service following Single Responsibility and Interface Segregation Principles.
"""

import base64
import logging
from typing import Dict, Any
import requests

from app.core.interfaces import IMessageService, ITokenManager
from app.core.config_provider import ServiceConfiguration
from app.utils.utils import retry_with_backoff


logger = logging.getLogger(__name__)


class DigisacMessageService(IMessageService):
    """Message service for Digisac following SRP and ISP"""

    def __init__(self, token_manager: ITokenManager):
        self.token_manager = token_manager
        self.base_url = ServiceConfiguration.DIGISAC_BASE_URL

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def send_text_message(
        self,
        contact_id: str,
        message: str,
        department_id: str = None,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """Send text message to contact"""
        payload = {
            "contactId": contact_id,
            "text": message,
            "origin": "bot",
        }

        if department_id:
            payload["ticketDepartmentId"] = department_id
        if user_id:
            payload["userId"] = user_id

        return self._send_message(payload)

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def send_file_message(
        self,
        contact_id: str,
        file_content: bytes,
        filename: str,
        message: str,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """Send file message to contact"""
        file_base64 = base64.b64encode(file_content).decode("utf-8")

        payload = {
            "text": message,
            "contactId": contact_id,
            "file": {
                "base64": file_base64,
                "mimetype": "application/pdf",
                "name": filename,
            },
        }

        if user_id:
            payload["userId"] = user_id

        return self._send_message(payload)

    def _send_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method to send message"""
        url = f"{self.base_url}/messages"
        headers = self.token_manager.get_auth_headers()

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return self._parse_response(response)
        except requests.RequestException as e:
            logger.error("Failed to send message: %s", e)
            return {"error": str(e)}

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse response from Digisac API"""
        content_type = response.headers.get("Content-Type", "")
        if response.content and "application/json" in content_type:
            try:
                data = response.json()
                logger.debug("Response JSON: %s", data)
                return data
            except ValueError:
                logger.warning("Invalid JSON response: %s", response.text)
                return {"status_code": response.status_code, "text": response.text}
        else:
            logger.debug("Non-JSON response: %s", response.text)
            return {"status_code": response.status_code, "text": response.text}
