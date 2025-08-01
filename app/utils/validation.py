# app/utils/validation.py
"""
Validation utilities following Single Responsibility Principle.
Each function has a single validation responsibility.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PhoneNumberValidator:
    """
    Phone number validation following Single Responsibility Principle.
    Handles Brazilian phone number standardization.
    """

    @staticmethod
    def standardize_phone_number(phone: str, debug: bool = False) -> Optional[str]:
        """
        Padroniza números de telefone brasileiros para formato
        internacional completo (DDI + DDD + número), sempre com 12 dígitos.

        :param phone: Número de telefone em qualquer formato
        :param debug: Habilita logs de warning para números inválidos
        :return: Número padronizado (ex: 556293159124) ou None se inválido
        """
        if not phone or not isinstance(phone, str):
            return None

        # Remove todos os não-dígitos
        digits = re.sub(r"\D", "", phone)
        n = len(digits)

        # Verificação de comprimento mínimo
        if n < 10 or n > 13:
            if debug:
                logger.warning(
                    f"Comprimento inválido para telefone brasileiro: {phone} (len={n})"
                )
            return None

        # Se já começa com 55 (DDI do Brasil)
        if digits.startswith("55"):
            # Se tem 13 dígitos: DDI (2) + DDD (2) + 9 + número (8)
            if n == 13:
                # Remove o 9 após o DDD
                ddi = digits[:2]
                ddd = digits[2:4]
                ninth_removed = digits[5:]  # pula o nono dígito
                return ddi + ddd + ninth_removed
            elif n == 12:
                return digits
            else:
                if debug:
                    logger.warning(f"Formato com DDI inválido: {phone} (len={n})")
                return None

        # Se tem 11 dígitos: DDD (2) + 9 + número (8)
        if n == 11:
            ddd = digits[:2]
            ninth_removed = digits[3:]  # pula o nono dígito
            return "55" + ddd + ninth_removed

        # Se tem 10 dígitos: DDD (2) + número (8)
        if n == 10:
            return "55" + digits

        # Se tem 9 dígitos apenas (número local sem DDD)
        if n == 9:
            # Assume DDD padrão 62 (Goiás) e remove o nono dígito
            return "5562" + digits[1:]

        if debug:
            logger.warning(f"Formato não suportado: {phone} (len={n})")
        return None
