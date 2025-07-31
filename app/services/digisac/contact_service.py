# app/services/digisac/contact_service.py
"""
Digisac contact service following Single Responsibility Principle.
"""

import json
import logging
from typing import Optional
from pathlib import Path

from app.core.interfaces import IContactService
from app.utils.utils import standardize_phone_number


logger = logging.getLogger(__name__)


class DigisacContactService(IContactService):
    """Contact service for Digisac following SRP"""

    def __init__(self, contacts_file_path: str):
        self.contacts_file_path = contacts_file_path

    def find_contact_by_phone(self, phone: str) -> Optional[str]:
        """Find contact ID by phone number with number variations support"""
        std_number = standardize_phone_number(phone, debug=True)
        logger.debug(f"Searching contact ID for standardized number: {std_number}")

        if not std_number:
            logger.warning(f"Could not standardize phone number: {phone}")
            return None

        try:
            # Generate variations for numbers with 13 digits (with ninth digit)
            possible_numbers = [std_number]
            if len(std_number) == 13:
                # Version without ninth digit: 55 (DDI) + 62 (DDD) + 93159124 (number)
                without_ninth = std_number[:4] + std_number[5:]
                possible_numbers.append(without_ninth)
                logger.debug(
                    f"Generated variation without ninth digit: {without_ninth}"
                )

            contacts = self._load_contacts()

            for contact in contacts:
                contact_num = (contact.get("data") or {}).get("number") or ""
                contact_std = standardize_phone_number(contact_num, debug=False)

                if contact_std in possible_numbers:
                    logger.debug(f"Contact found: {contact_std} => {contact.get('id')}")
                    return contact.get("id")

            logger.warning(f"No contact found for: {std_number}")
            return None

        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.error(f"Error searching contact ID: {str(e)}")
            return None

    def find_contact_by_document(self, document: str) -> Optional[str]:
        """Find contact ID by document (not implemented for Digisac)"""
        # Digisac doesn't store documents in contacts
        return None

    def get_contact_phone_by_id(self, contact_id: str) -> Optional[str]:
        """Get contact phone number by ID"""
        try:
            contacts = self._load_contacts()

            for contact in contacts:
                if contact.get("id") == contact_id:
                    return (contact.get("data") or {}).get("number")

        except Exception as e:
            logger.error(f"Error getting contact by ID: {str(e)}")

        return None

    def _load_contacts(self) -> list:
        """Load contacts from JSON file"""
        contacts_path = Path(self.contacts_file_path)

        with open(contacts_path, "r", encoding="utf-8") as f:
            return json.load(f)
