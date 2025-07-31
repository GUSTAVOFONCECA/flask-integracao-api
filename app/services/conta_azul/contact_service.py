# app/services/conta_azul/contact_service.py
"""
Conta Azul contact service following Single Responsibility Principle.
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional

from app.core.interfaces import IContactService
from app.utils.utils import standardize_phone_number, debug


logger = logging.getLogger(__name__)


class ContaAzulContactService(IContactService):
    """Contact service for Conta Azul following SRP"""

    def __init__(self, persons_file_path: str):
        self.persons_file_path = persons_file_path

    @debug
    def find_contact_by_phone(self, phone: str) -> Optional[str]:
        """Find person UUID by phone number"""
        # Standardize phone number to international format
        std_number = standardize_phone_number(phone, debug=True)
        if not std_number:
            logger.warning(f"Phone number {phone} could not be standardized")
            return None

        # Convert to Conta Azul format (remove DDI 55 and keep DDD + number)
        if len(std_number) == 13:  # Complete format: 55 + DDD + 9 digits
            conta_azul_number = std_number[2:]  # Remove DDI (55)
        elif len(std_number) == 12:  # Format without ninth: 55 + DDD + 8 digits
            # Convert to format with ninth digit (Brazilian standard)
            conta_azul_number = std_number[2:4] + "9" + std_number[4:]
        else:
            logger.warning(f"Unsupported format: {std_number} (len={len(std_number)})")
            return None

        logger.debug(f"Searching client in Conta Azul format: {conta_azul_number}")

        persons = self._load_persons()

        for person in persons.get("itens", []):
            person_phone = person.get("telefone")
            if not person_phone:
                continue

            # Standardize client phone from Conta Azul
            person_digits = re.sub(r"\D", "", person_phone)

            # Compare directly with Conta Azul format
            if person_digits == conta_azul_number:
                return person["uuid"]

        logger.warning(f"Client not found for: {phone} -> {conta_azul_number}")
        return None

    @debug
    def find_contact_by_document(self, document: Optional[str]) -> Optional[str]:
        """Find person UUID by CPF or CNPJ"""
        if not isinstance(document, str):
            logger.warning(f"Invalid document (not string): {document}")
            return None

        # Remove any mask (dots, dashes, slashes)
        digits = re.sub(r"\D", "", document)
        if not digits:
            logger.warning(f"Invalid or empty document after cleaning: {document}")
            return None

        persons = self._load_persons()

        for person in persons.get("itens", []):
            raw_doc = person.get("documento")
            if not isinstance(raw_doc, str):
                continue  # ignore null or invalid documents

            person_doc = re.sub(r"\D", "", raw_doc)
            if person_doc == digits:
                return person.get("uuid")

        logger.warning(f"Client not found for document: {document}")
        return None

    def _load_persons(self) -> dict:
        """Load persons from JSON file"""
        persons_path = Path(self.persons_file_path)

        with open(persons_path, "r", encoding="utf-8") as f:
            return json.load(f)
