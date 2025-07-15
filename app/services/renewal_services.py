# app/services/renewal_services.py

import logging
import sqlite3
import hashlib
import json
from app.database.database import get_db_connection
from app.utils import standardize_phone_number

logger = logging.getLogger(__name__)


def _standardize_phone(phone: str) -> str:
    """Padroniza números para formato internacional (13 dígitos)"""
    if not phone:
        return ""

    try:
        std_phone = standardize_phone_number(phone)
        if std_phone and len(std_phone) == 12:
            return std_phone[:4] + "9" + std_phone[4:]
        return std_phone
    except Exception:
        return phone  # Retorna o original em caso de erro


# renewal_services.py
def add_pending(
    company_name: str, contact_number: str, deal_type: str, spa_id: int
) -> str:
    std_number = _standardize_phone(contact_number)
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO certif_pending_renewals (
                    company_name, contact_number, deal_type, spa_id
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(spa_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    contact_number = excluded.contact_number,
                    deal_type = excluded.deal_type
                """,
                (company_name, std_number, deal_type, spa_id),
            )
            conn.commit()
        return std_number
    except Exception as e:
        logger.error(f"Erro ao adicionar pendência: {str(e)}")
        raise


def update_pending(spa_id: str, status: str, **kwargs) -> bool:
    set_clauses = []
    params = []
    for field, value in kwargs.items():
        if value is not None:
            set_clauses.append(f"{field} = COALESCE({field}, ?)")
            params.append(value)

    if status:
        set_clauses.append("status = ?")
        params.append(status)

    if not set_clauses:
        return False

    params.append(spa_id)
    sql = (
        f"UPDATE certif_pending_renewals SET {', '.join(set_clauses)} WHERE spa_id = ?"
    )

    try:
        with get_db_connection() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar: {e}")
        raise


def complete_pending(contact_number: str) -> bool:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM certif_pending_renewals WHERE contact_number = ?",
            (std_number,),
        )
        return cur.rowcount > 0


def get_pending(contact_number: str = None, spa_id: int = None) -> dict | None:
    if not any([contact_number, spa_id]):
        raise ValueError("É necessário fornecer contact_number, contact_id ou spa_id.")

    with get_db_connection() as conn:
        row = None

        if contact_number:
            std_number = _standardize_phone(contact_number)
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE contact_number = ?",
                (std_number,),
            ).fetchone()

        if not row and spa_id:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE spa_id = ?",
                (spa_id,),
            ).fetchone()

        return dict(row) if row else None


def check_pending_status(spa_id: int, status: str) -> bool:
    """Verifica se a pendência já está em um estado específico"""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM certif_pending_renewals WHERE spa_id = ? AND status = ?",
            (spa_id, status),
        ).fetchone()
        return row is not None


# Gera hash SHA256 de um payload para auditoria
def compute_hash(payload: dict | str) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Verifica se há registro de event para message_id
def is_message_processed(message_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM message_events WHERE message_id = ?",
            (message_id,),
        )
        return cur.fetchone() is not None


# Registra um novo evento; IntegrityError ⇨ duplicado
def mark_message_processed(
    spa_id: int, message_id: str, event_type: str, payload: dict | str
) -> bool:
    """
    Tenta inserir novo evento.

    Returns:
        (True) se inseriu.
        (False) se já existe.
    """
    payload_hash = compute_hash(payload)
    with get_db_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO message_events(spa_id, message_id, event_type, payload_hash)
                VALUES (?, ?, ?, ?)
                """,
                (spa_id, message_id, event_type, payload_hash),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
