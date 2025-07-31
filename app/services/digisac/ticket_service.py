# app/services/digisac/ticket_service.py
"""
Digisac ticket service following Single Responsibility and Interface Segregation Principles.
"""

import json
import logging
import urllib.parse
from typing import Dict, Any, Optional
import requests

from app.core.interfaces import ITicketService, ITokenManager
from app.core.config_provider import ServiceConfiguration
from app.utils.utils import retry_with_backoff


logger = logging.getLogger(__name__)


class DigisacTicketService(ITicketService):
    """Ticket service for Digisac following SRP and ISP"""

    def __init__(self, token_manager: ITokenManager):
        self.token_manager = token_manager
        self.base_url = ServiceConfiguration.DIGISAC_BASE_URL

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def transfer_ticket(
        self, contact_id: str, department_id: str, comments: str, user_id: str = None
    ) -> Dict[str, Any]:
        """Transfer ticket to department or user"""
        payload = {
            "departmentId": department_id,
            "comments": comments,
            "contactId": contact_id,
        }

        if user_id:
            payload["userId"] = user_id

        url = f"{self.base_url}/contacts/{contact_id}/ticket/transfer"
        headers = self.token_manager.get_auth_headers()

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return self._parse_response(response)
        except requests.RequestException as e:
            logger.error("Failed to transfer ticket: %s", e)
            return {"error": str(e)}

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def close_ticket(self, contact_id: str) -> Dict[str, Any]:
        """Close ticket for contact"""
        url = f"{self.base_url}/contacts/{contact_id}/ticket/close"
        headers = self.token_manager.get_auth_headers()

        try:
            response = requests.post(url, headers=headers, timeout=60)
            response.raise_for_status()
            return self._parse_response(response)
        except requests.RequestException as e:
            logger.error("Failed to close ticket: %s", e)
            return {"error": str(e)}

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def has_open_ticket(
        self, contact_id: str, exclude_department_id: str = None
    ) -> bool:
        """Check if contact has open ticket"""
        ticket = self._fetch_open_ticket(contact_id)
        if not ticket:
            return False

        # If excluding a specific department, check if ticket is in that department
        if exclude_department_id:
            return ticket.get("departmentId") != exclude_department_id

        return True

    def _fetch_open_ticket(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch open ticket for contact"""
        query = {
            "where": {"isOpen": True},
            "include": [
                {
                    "model": "contact",
                    "required": True,
                    "where": {"visible": True, "id": contact_id},
                }
            ],
        }

        encoded_query = urllib.parse.quote(json.dumps(query))
        url = f"{self.base_url}/tickets?query={encoded_query}"
        headers = self.token_manager.get_auth_headers()

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = data.get("data", []) or []
            return items[0] if items else None
        except requests.RequestException as e:
            logger.error("Failed to fetch open ticket: %s", e)
            return None

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
