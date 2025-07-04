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


def add_pending(
    company_name: str,
    contact_number: str,
    deal_type: str,
    spa_id: int,
    digisac_contact_id: str = None,
) -> str:
    std_number = _standardize_phone(contact_number)
    logger.info(
        f"Adicionando pendência: {std_number} - {deal_type} - Card SPA: {spa_id}"
    )

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO certif_pending_renewals (
                    company_name,
                    contact_number,
                    deal_type,
                    spa_id,
                    digisac_contact_id
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_name, std_number, deal_type, spa_id, digisac_contact_id),
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


def update_pending(
    spa_id: str, status: str, sale_id: str = None, financial_event_id: str = None
) -> bool:
    """
    Atualiza campos da pendência apenas se os argumentos não forem None.
    Apenas statuses permitidos podem ser usados.
    """
    ALLOWED_STATUSES = {
        "pending",
        "customer_retention",
        "sale_created",
        "billing_generated",
        "billing_pdf_sent",
        "scheduling_form_sent",
    }

    logger.info(
        f"Atualizando pendência: {spa_id} "
        f"com sale_id={sale_id}, financial_event_id={financial_event_id}, status={status}"
    )

    # Valida status
    if status is not None and status not in ALLOWED_STATUSES:
        msg = f"Status inválido para pendência: {status}"
        logger.warning(msg)
        raise ValueError(msg)

    # Monta dinamicamente as colunas a atualizar
    set_clauses = []
    params = []
    if sale_id is not None:
        set_clauses.append("sale_id = ?")
        params.append(sale_id)
    if financial_event_id is not None:
        set_clauses.append("financial_event_id = ?")
        params.append(financial_event_id)
    if status is not None:
        set_clauses.append("status = ?")
        params.append(status)

    # Se nenhum campo para atualizar, aborta
    if not set_clauses:
        logger.warning(f"Nenhum campo para atualizar para pendência {spa_id}")
        return False

    sql = f"""
        UPDATE certif_pending_renewals
        SET {', '.join(set_clauses)}
        WHERE spa_id = ?
    """
    params.append(spa_id)

    try:
        with get_db_connection() as conn:
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            updated = cur.rowcount > 0
            if updated:
                logger.info(f"Pendência atualizada: {spa_id}")
            else:
                logger.warning(
                    f"Nenhuma pendência encontrada para atualizar: {spa_id}"
                )
            return updated
    except Exception as e:
        logger.error(f"Erro ao atualizar pendência: {e}")
        raise


def complete_pending(contact_number: str) -> bool:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM certif_pending_renewals WHERE contact_number = ?",
            (std_number,),
        )
        return cur.rowcount > 0


def get_pending(contact_number: str = None, contact_id: str = None) -> dict | None:
    if not contact_number and not contact_id:
        raise ValueError("É necessário fornecer contact_number ou contact_id")

    with get_db_connection() as conn:
        if contact_number:
            std_number = _standardize_phone(contact_number)
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE contact_number = ?",
                (std_number,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE digisac_contact_id = ?",
                (contact_id,),
            ).fetchone()

        return dict(row) if row else None
