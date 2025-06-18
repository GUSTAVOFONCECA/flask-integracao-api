# app/services/renewal_services.py

import logging
import sqlite3
from app.database.database import get_db_connection
from app.utils import standardize_phone_number

logger = logging.getLogger(__name__)


def _standardize_phone(phone: str) -> str:
    """Padroniza números para formato internacional (13 dígitos)"""
    # Primeiro padroniza usando a função existente
    std_phone = standardize_phone_number(phone)

    # Se veio sem nono dígito (12 dígitos), converte para 13
    if std_phone and len(std_phone) == 12:
        # Formato: 55 (DDI) + 62 (DDD) + 93159124 (número)
        return std_phone[:4] + "9" + std_phone[4:]

    return std_phone


def add_pending(contact_number: str, deal_type: str) -> str:
    std_number = _standardize_phone(contact_number)
    logger.info(f"Adicionando pendência: {std_number} - {deal_type}")

    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO certif_pending_renewals (contact_number, deal_type) VALUES (?, ?)",
                (std_number, deal_type),
            )
            conn.commit()
        logger.info(f"Pendência inserida com sucesso: {std_number}")
        return std_number
    except sqlite3.IntegrityError:
        logger.warning(f"Pendência já existe: {std_number}")
        return std_number
    except Exception as e:
        logger.error(f"Erro ao inserir pendência: {str(e)}")
        raise


def update_pending_sale(
    contact_number: str, sale_id: str, billing_id: str, pdf_url: str
) -> bool:
    std_number = standardize_phone_number(contact_number)
    logger.info(
        f"Atualizando pendência: {std_number} com sale_id {sale_id}, billing_id {billing_id}"
    )

    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                """UPDATE certif_pending_renewals 
                SET sale_id = ?, billing_id = ?, pdf_url = ?, status = 'billing_created' 
                WHERE contact_number = ?""",
                (sale_id, billing_id, pdf_url, std_number),
            )
            conn.commit()
            updated = cur.rowcount > 0
            if updated:
                logger.info(f"Pendência atualizada: {std_number}")
            else:
                logger.warning(
                    f"Nenhuma pendência encontrada para atualizar: {std_number}"
                )
            return updated
    except Exception as e:
        logger.error(f"Erro ao atualizar pendência: {str(e)}")
        raise


def complete_pending(contact_number: str) -> bool:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM certif_pending_renewals WHERE contact_number = ?",
            (std_number,),
        )
        return cur.rowcount > 0


def get_pending(contact_number: str) -> dict | None:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM certif_pending_renewals WHERE contact_number = ?",
            (std_number,),
        ).fetchone()
        return dict(row) if row else None
