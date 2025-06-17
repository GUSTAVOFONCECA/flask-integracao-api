# app/services/renewal_services.py

import json
import logging
from pathlib import Path
from app.utils import standardize_phone_number

logger = logging.getLogger(__name__)
PENDING_FILE = Path("app/database/pending_renewals.json")


def _load_pending():
    try:
        if PENDING_FILE.exists():
            content = PENDING_FILE.read_text(encoding="utf-8").strip()
            if content:  # Verifica se o arquivo não está vazio
                return json.loads(content)
            return {}
        return {}
    except Exception as e:
        logger.error(f"Erro ao carregar pendências: {str(e)}")
        return {}  # Retorna dict vazio em caso de erro


def _standardize_phone(phone: str) -> str:
    """Padroniza números para formato internacional (13 dígitos)"""
    # Primeiro padroniza usando a função existente
    std_phone = standardize_phone_number(phone)

    # Se veio sem nono dígito (12 dígitos), converte para 13
    if std_phone and len(std_phone) == 12:
        # Formato: 55 (DDI) + 62 (DDD) + 93159124 (número)
        return std_phone[:4] + "9" + std_phone[4:]

    return std_phone


def _save_pending(data):
    try:
        PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        PENDING_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug(f"Pendências salvas: {len(data)} registros")
    except Exception as e:
        logger.error(f"Erro ao salvar pendências: {str(e)}")


def add_pending(contact_number: str, deal_type: str):
    std_number = _standardize_phone(contact_number)
    logger.debug(f"Adicionando pendência: {std_number} => {deal_type}")

    pending = _load_pending()
    pending[std_number] = deal_type
    _save_pending(pending)

    return std_number  # Retorna o número padronizado para debug


def pop_pending(contact_number: str) -> str | None:
    std_number = _standardize_phone(contact_number)
    logger.debug(f"Removendo pendência: {std_number}")

    pending = _load_pending()
    deal_type = pending.pop(std_number, None)

    if deal_type:
        _save_pending(pending)
        return deal_type
    return None


def get_pending(contact_number: str) -> str | None:
    """Consulta uma pendência sem removê-la"""
    std_number = _standardize_phone(contact_number)
    logger.debug(f"Consultando pendência: {std_number}")
    pending = _load_pending()
    return pending.get(std_number)
