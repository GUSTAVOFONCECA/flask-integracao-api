# app/services/renewal_services.py
import logging
import sqlite3
import hashlib
import json
from typing import Optional
from app.database.database import get_db_connection
from app.utils.utils import standardize_phone_number

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


def update_pending(spa_id: int, status: str, **kwargs) -> bool:
    """Atualiza uma pendência, focando no campo de status e outros opcionais."""
    # Garante que spa_id seja um inteiro para a consulta
    if not isinstance(spa_id, int):
        try:
            spa_id = int(spa_id)
        except (ValueError, TypeError):
            logger.error(f"ID do SPA inválido fornecido para atualização: {spa_id}")
            return False

    update_fields = {"status": status}
    update_fields.update(kwargs)

    # Constrói a query dinamicamente para atualizar apenas os campos fornecidos
    set_clauses = [f"{field} = ?" for field in update_fields.keys()]
    params = list(update_fields.values())
    params.append(spa_id)

    sql = (
        f"UPDATE certif_pending_renewals SET {', '.join(set_clauses)} WHERE spa_id = ?"
    )

    try:
        with get_db_connection() as conn:
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            logger.info(
                f"Pendência para SPA ID {spa_id} atualizada com: {update_fields}"
            )
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar pendência para SPA ID {spa_id}: {e}")
        raise


def complete_pending(contact_number: str) -> bool:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM certif_pending_renewals WHERE contact_number = ?",
            (std_number,),
        )
        return cur.rowcount > 0


def get_pending(contact_number: str = None, spa_id: int = None) -> Optional[dict]:
    """
    Obtém uma pendência de renovação.
    - Se spa_id for fornecido, a busca é direta e unívoca.
    - Se contact_number for fornecido, retorna a pendência mais recente que não esteja
      em um estado final (como 'customer_retention').
    """
    if not any([contact_number, spa_id]):
        raise ValueError("É necessário fornecer contact_number ou spa_id.")

    with get_db_connection() as conn:
        row = None

        if spa_id:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE spa_id = ?", (int(spa_id),)
            ).fetchone()
        elif contact_number:
            std_number = _standardize_phone(contact_number)
            # Busca a pendência mais recente que ainda espera uma ação do cliente.
            row = conn.execute(
                """
                SELECT * FROM certif_pending_renewals
                WHERE contact_number = ?
                AND status NOT IN ('customer_retention', 'scheduling_form_sent')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (std_number,),
            ).fetchone()

        return dict(row) if row else None


def check_pending_status(spa_id: int) -> Optional[str]:
    """Verifica o status atual de uma pendência no banco de dados para um dado SPA ID."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT status FROM certif_pending_renewals WHERE spa_id = ?",
            (int(spa_id),),
        )
        row = cursor.fetchone()
        return row["status"] if row else None


def compute_hash(payload: dict | str) -> str:
    """Gera hash SHA256 de um payload para auditoria e deduplicação."""
    text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_message_processed(message_id: str) -> bool:
    """Verifica na tabela de eventos se uma mensagem com este ID já foi processada."""
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM message_events WHERE message_id = ?", (message_id,)
        )
        return cur.fetchone() is not None


def mark_message_processed(
    spa_id: int, message_id: str, event_type: str, payload: dict | str
) -> bool:
    """
    Registra um novo evento de mensagem no banco de dados.
    Retorna True se a inserção for bem-sucedida, e False se a mensagem já existir
    (indicando uma duplicata).
    """
    payload_hash = compute_hash(payload)
    with get_db_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO message_events (spa_id, message_id, event_type, payload_hash)
                VALUES (?, ?, ?, ?)
                """,
                (int(spa_id), message_id, event_type, payload_hash),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Isso acontece se o message_id (UNIQUE) já existir, o que é esperado
            # em cenários de webhooks duplicados.
            logger.warning(
                f"Tentativa de inserir message_id duplicado: {message_id} para SPA ID {spa_id}"
            )
            return False
