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
    digisac_ticket_id: str = None,
) -> str:
    std_number = _standardize_phone(contact_number)
    logger.info(
        f"Adicionando/Atualizando pendência: {std_number} | SPA: {spa_id} | Ticket: {digisac_ticket_id}"
    )

    try:
        with get_db_connection() as conn:
            # Verifica se já existe uma pendência para este SPA
            existing = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE spa_id = ?", (spa_id,)
            ).fetchone()

            if existing:
                # Atualiza apenas se novos IDs estiverem disponíveis
                new_contact_id = digisac_contact_id or existing["digisac_contact_id"]
                new_ticket_id = digisac_ticket_id or existing["digisac_ticket_id"]

                conn.execute(
                    """
                    UPDATE certif_pending_renewals
                    SET digisac_contact_id = ?,
                        digisac_ticket_id = ?
                    WHERE spa_id = ?
                    """,
                    (new_contact_id, new_ticket_id, spa_id),
                )
                logger.info(f"Pendência atualizada para SPA {spa_id}")
                return std_number

            # Insere nova pendência
            conn.execute(
                """
                INSERT INTO certif_pending_renewals (
                    company_name,
                    contact_number,
                    deal_type,
                    spa_id,
                    digisac_contact_id,
                    digisac_ticket_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company_name,
                    std_number,
                    deal_type,
                    spa_id,
                    digisac_contact_id,
                    digisac_ticket_id,
                ),
            )
            conn.commit()

        logger.info(f"Nova pendência criada com sucesso: {std_number}")
        return std_number

    except sqlite3.IntegrityError as e:
        logger.warning(f"Conflito de integridade: {str(e)}")
        return std_number
    except Exception as e:
        logger.error(f"Erro ao processar pendência: {str(e)}")
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
        "info_sent",
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
    # Só atualiza sale_id se ainda não existir
    if sale_id is not None:
        set_clauses.append("sale_id = COALESCE(sale_id, ?)")
        params.append(sale_id)

    # Só atualiza financial_event_id se ainda não existir
    if financial_event_id is not None:
        set_clauses.append("financial_event_id = COALESCE(financial_event_id, ?)")
        params.append(financial_event_id)

    # Atualiza status se fornecido
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
                logger.warning(f"Nenhuma pendência encontrada para atualizar: {spa_id}")
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


def get_pending(
    contact_number: str = None, contact_id: str = None, spa_id: int = None
) -> dict | None:
    if not any([contact_number, contact_id, spa_id]):
        raise ValueError("É necessário fornecer contact_number, contact_id ou spa_id.")

    with get_db_connection() as conn:
        row = None

        if contact_number:
            std_number = _standardize_phone(contact_number)
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE contact_number = ?",
                (std_number,),
            ).fetchone()

        if not row and contact_id:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE digisac_contact_id = ?",
                (contact_id,),
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


def has_active_ticket(contact_id: str) -> bool:
    """Verifica se já existe um ticket ativo para este contato"""
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 
            FROM certif_pending_renewals 
            WHERE digisac_contact_id = ? 
              AND status NOT IN ('completed', 'closed')
            """,
            (contact_id,),
        ).fetchone()
        return row is not None


def is_message_processed(message_id: str) -> bool:
    """Verifica se uma mensagem já foi processada"""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row is not None


def mark_message_processed(message_id: str):
    """Registra uma mensagem como processada"""
    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO processed_messages (message_id) VALUES (?)", (message_id,)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Mensagem já registrada, ignora
            pass
