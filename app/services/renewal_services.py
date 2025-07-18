# app/services/renewal_services.py
import logging
import sqlite3
import json
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Callable
from app.database.database import get_db_connection
from app.utils.utils import standardize_phone_number, debug

logger = logging.getLogger(__name__)


def _standardize_phone(phone: str) -> str:
    if not phone:
        return ""
    try:
        std_phone = standardize_phone_number(phone)
        if std_phone and len(std_phone) == 12:
            return std_phone[:4] + "9" + std_phone[4:]
        return std_phone
    except Exception:
        return phone


# Funções principais
@debug
def add_pending(
    company_name: str,
    contact_number: str,
    contact_name: str,
    deal_type: str,
    spa_id: int,
) -> str:
    std_number = _standardize_phone(contact_number)
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO certif_pending_renewals (
                    company_name, contact_number, contact_name, deal_type, spa_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(spa_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    contact_number = excluded.contact_number,
                    contact_name = excluded.contact_name,
                    deal_type = excluded.deal_type
                """,
                (company_name, std_number, contact_name, deal_type, spa_id),
            )
            conn.commit()
        return std_number
    except Exception as e:
        logger.error(f"Erro ao adicionar pendência: {str(e)}")
        raise


@debug
def update_pending(spa_id: int, status: str, **kwargs) -> bool:
    if not isinstance(spa_id, int):
        try:
            spa_id = int(spa_id)
        except (ValueError, TypeError):
            logger.error(f"ID do SPA inválido: {spa_id}")
            return False

    update_fields = {"status": status, "last_interaction": datetime.now()}
    update_fields.update(kwargs)

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
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar SPA {spa_id}: {e}")
        raise


@debug
def get_pending(
    contact_number: str = None, spa_id: int = None, context_aware: bool = False
) -> Optional[dict]:
    if not any([contact_number, spa_id]):
        raise ValueError("Necessário contact_number ou spa_id")

    with get_db_connection() as conn:
        if spa_id:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE spa_id = ?", (int(spa_id),)
            ).fetchone()
            return dict(row) if row else None

        std_number = _standardize_phone(contact_number)
        query = """
            SELECT * FROM certif_pending_renewals
            WHERE contact_number = ?
            AND status NOT IN ('customer_retention', 'scheduling_form_sent', 'complete')
            ORDER BY {}
            LIMIT 1
        """

        if context_aware:
            final_query = query.format(
                """
                CASE WHEN last_interaction IS NULL THEN 0 ELSE 1 END, 
                last_interaction ASC
            """
            )
        else:
            final_query = query.format("created_at DESC")

        row = conn.execute(final_query, (std_number,)).fetchone()
        return dict(row) if row else None


# Funções de processamento e filas
@debug
def is_contact_processing(spa_id: int) -> bool:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT is_processing FROM certif_pending_renewals WHERE spa_id = ?",
            (spa_id,),
        ).fetchone()
        return row and row["is_processing"] == 1


def set_processing_status(spa_id: int, status: bool):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE certif_pending_renewals SET is_processing = ? WHERE spa_id = ?",
            (1 if status else 0, spa_id),
        )
        conn.commit()


# Adicionar nova função para enfileirar mensagens
@debug
def add_pending_message(spa_id: int, payload: dict) -> int:
    with get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO pending_messages (spa_id, payload) VALUES (?, ?)",
            (spa_id, json.dumps(payload)),
        )
        conn.commit()
        return cur.lastrowid


# Nova função para processar fila
@debug
def process_pending_messages(spa_id: int, handler: Callable[[int, str], None]):
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, payload FROM pending_messages "
            "WHERE spa_id = ? AND processed = 0 "
            "ORDER BY created_at ASC",
            (spa_id,),
        ).fetchall()

        for row in rows:
            payload = json.loads(row["payload"])
            # Marca como processado ANTES de disparar o handler
            conn.execute(
                "UPDATE pending_messages SET processed = 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()

            # Extrai a mensagem e chama o handler injetado
            text = payload.get("data", {}).get("message", {}).get("text", "")
            handler(spa_id, text)


@debug
def get_next_pending_message(spa_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, payload FROM pending_messages "
            "WHERE spa_id = ? AND processed = 0 "
            "ORDER BY created_at ASC LIMIT 1",
            (spa_id,),
        ).fetchone()
        return dict(row) if row else None


# Funções de mensagens e notificações
@debug
def mark_message_processed(
    spa_id: int, message_id: str, event_type: str, payload: dict
) -> bool:
    """Armazena payload completo em vez de hash"""
    try:
        payload_json = json.dumps(payload)
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO message_events (spa_id, message_id, event_type, payload) "
                "VALUES (?, ?, ?, ?)",
                (spa_id, message_id, event_type, payload_json),
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        logger.warning(f"Message_id duplicado: {message_id} para SPA {spa_id}")
        return False


@debug
def is_message_processed(message_id: str) -> bool:
    """Verifica se mensagem já foi processada"""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM message_events WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None


@debug
def has_recent_notification(
    spa_id: int, notification_type: str, minutes: int = 5
) -> bool:
    time_threshold = datetime.now() - timedelta(minutes=minutes)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM message_events "
            "WHERE spa_id = ? AND event_type = ? AND created_at >= ?",
            (spa_id, notification_type, time_threshold),
        ).fetchone()
        return row is not None


@debug
def is_message_in_queue(spa_id: int, message_id: str) -> bool:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM pending_messages "
            "WHERE spa_id = ? AND payload LIKE ? AND processed = 0",
            (spa_id, f'%"id":"{message_id}"%'),
        ).fetchone()
        return row is not None


@debug
def is_message_processed_or_queued(spa_id: int, message_id: str) -> bool:
    return is_message_processed(message_id) or is_message_in_queue(spa_id, message_id)


@debug
def get_contact_number_by_spa_id(spa_id: int) -> Optional[str]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT contact_number FROM certif_pending_renewals WHERE spa_id = ?",
            (spa_id,),
        ).fetchone()
        return row["contact_number"] if row else None
    

@debug
def _get_contact_number_by_digisac_id(contact_id: str) -> Optional[str]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT "
        )


@debug
def mark_notification_event(spa_id: int, notification_type: str):
    message_id = f"notif-{int(time.time())}-{random.randint(1000,9999)}"
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO message_events (spa_id, message_id, event_type, payload_hash) "
            "VALUES (?, ?, ?, ?)",
            (spa_id, message_id, notification_type, "notification"),
        )
        conn.commit()


@debug
def get_active_spa_id(contact_number: str) -> Optional[int]:
    """Obtém o SPA_ID ativo para um número"""
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT spa_id FROM certif_pending_renewals "
            "WHERE contact_number = ? AND status NOT IN ('complete', 'expired') "
            "ORDER BY last_interaction DESC LIMIT 1",
            (std_number,),
        ).fetchone()
        return row["spa_id"] if row else None


@debug
def get_all_pending_by_contact(contact_number: str) -> list[dict]:
    std_number = _standardize_phone(contact_number)
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM certif_pending_renewals "
            "WHERE contact_number = ? AND status NOT IN ('customer_retention', 'scheduling_form_sent') "
            "ORDER BY created_at ASC",
            (std_number,),
        ).fetchall()
        return [dict(row) for row in rows]


@debug
def try_lock_processing(spa_id: int) -> bool:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT is_processing FROM certif_pending_renewals WHERE spa_id = ?",
            (spa_id,),
        ).fetchone()
        if row and row["is_processing"] == 0:
            conn.execute(
                "UPDATE certif_pending_renewals SET is_processing = 1 WHERE spa_id = ?",
                (spa_id,),
            )
            conn.commit()
            return True
    return False
