# app/utils/phone_utils.py

"""
Phone number utilities following SOLID principles.
Implements Single Responsibility principle.
"""

import re
import logging
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class IPhoneFormatter(ABC):
    """Interface for phone number formatting"""

    @abstractmethod
    def format_phone(self, phone: str) -> Optional[str]:
        """Format phone number"""
        pass


class BrazilianPhoneFormatter(IPhoneFormatter):
    """Brazilian phone number formatter"""

    def format_phone(self, phone: str) -> Optional[str]:
        """
        Standardize Brazilian phone numbers to international format
        with 12 digits (DDI + DDD + number).

        :param phone: Phone number in any format
        :return: Standardized number (e.g., 556293159124) or None if invalid
        """
        if not phone or not isinstance(phone, str):
            return None

        # Remove all non-digits
        digits = re.sub(r"\D", "", phone)
        n = len(digits)

        # Check minimum length
        if n < 10 or n > 13:
            logger.warning(f"Invalid length for Brazilian phone: {phone} (len={n})")
            return None

        # If already starts with 55 (Brazil country code)
        if digits.startswith("55"):
            if n == 13:
                # Remove the 9th digit after area code
                ddi = digits[:2]
                ddd = digits[2:4]
                number = digits[5:]  # skip 9th digit
                return ddi + ddd + number
            elif n == 12:
                return digits
            else:
                logger.warning(f"Invalid format with country code: {phone} (len={n})")
                return None

        # If 11 digits: area code (2) + 9 + number (8)
        if n == 11:
            ddd = digits[:2]
            number = digits[3:]  # skip 9th digit
            return "55" + ddd + number

        # If 10 digits: area code (2) + number (8)
        if n == 10:
            return "55" + digits

        # If 9 digits (local number without area code)
        if n == 9:
            # Assume default area code 62 (Goiás) and remove 9th digit
            return "5562" + digits[1:]

        logger.warning(f"Unsupported format: {phone} (len={n})")
        return None


def standardize_phone_number(phone: str, debug: bool = False) -> Optional[str]:
    """
    Convenience function to standardize Brazilian phone numbers.

    :param phone: Phone number in any format
    :param debug: Enable debug logging for invalid numbers
    :return: Standardized number or None if invalid
    """
    if debug:
        # Configure logger to show warnings
        logging.getLogger(__name__).setLevel(logging.WARNING)

    formatter = BrazilianPhoneFormatter()
    return formatter.format_phone(phone)
