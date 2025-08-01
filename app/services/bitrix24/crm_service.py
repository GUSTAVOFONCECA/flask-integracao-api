# app/services/bitrix24/crm_service.py
"""
Bitrix24 CRM service following Single Responsibility Principle.
"""

import logging
from typing import Dict, Any, Optional, List
import requests

from app.core.interfaces import ICRMService
from app.utils.utils import debug


logger = logging.getLogger(__name__)


class BitrixCRMService(ICRMService):
    """CRM service for Bitrix24 following SRP"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    @debug
    def get_item(self, entity_type_id: int, item_id: int) -> Dict[str, Any]:
        """Get CRM item"""
        url = f"{self.base_url}/crm.item.get"
        query = {
            "entityTypeId": entity_type_id,
            "id": item_id,
            "useOriginalUfNames": "Y",
        }

        try:
            response = requests.get(url, params=query, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting CRM item: {str(e)}")
            return {"error": str(e)}

    @debug
    def update_item(
        self, entity_type_id: int, item_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update CRM item"""
        url = f"{self.base_url}/crm.item.update"
        payload = {
            "entityTypeId": entity_type_id,
            "id": item_id,
            "fields": fields,
        }

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating CRM item: {str(e)}")
            return {"error": str(e)}

    @debug
    def get_deal(self, deal_id: int) -> Dict[str, Any]:
        """Get deal item"""
        url = f"{self.base_url}/crm.deal.get"
        query = {"id": deal_id}

        try:
            response = requests.get(url, params=query, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting deal: {str(e)}")
            return {"error": str(e)}

    @debug
    def update_deal(
        self, entity_type_id: int, deal_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update deal item"""
        url = f"{self.base_url}/crm.deal.update"
        payload = {
            "entityTypeId": entity_type_id,
            "id": deal_id,
            "fields": fields,
        }

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            logger.debug(f"Response: {response.json()}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating deal: {str(e)}")
            return {"error": str(e)}

    @debug
    def add_timeline_comment(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Add comment to CRM timeline"""
        url = f"{self.base_url}/crm.timeline.comment.add"
        payload = {"fields": fields}

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding timeline comment: {str(e)}")
            return {"error": str(e)}

    @debug
    def start_workflow(
        self,
        template_id: int,
        document_id: List[str],
        parameters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Start business process workflow"""
        url = f"{self.base_url}/bizproc.workflow.start"
        payload = {
            "TEMPLATE_ID": template_id,
            "DOCUMENT_ID": document_id,
            "PARAMETERS": parameters or {},
        }

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error starting workflow: {str(e)}")
            return {"error": str(e)}
