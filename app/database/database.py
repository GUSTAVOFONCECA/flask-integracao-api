# app/database.py
import os
import sqlite3
from contextlib import contextmanager

DB_DIR = os.path.join(os.getcwd(), "app", "database")
DB_PATH = os.path.join(DB_DIR, "integrations.db")


@contextmanager
def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # habilita enforcement de FKs
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Inicializa o esquema de banco de dados para:
      - certif_pending_renewals: armazena estágios do negócio
      - message_events: rastreia mensagens e ações realizadas

    A deduplicação de webhooks se dá pelo _unique_ message_id em message_events.
    """
    with get_db_connection() as conn:
        # database.py - Schema otimizado

        # Tabela principal de pendências
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certif_pending_renewals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                spa_id           INTEGER NOT NULL UNIQUE,
                company_name     TEXT    NOT NULL,
                contact_name     TEXT    NOT NULL,
                contact_number   TEXT    NOT NULL,
                deal_type        TEXT    NOT NULL,
                sale_id          TEXT,
                financial_event_id TEXT,
                status           TEXT    NOT NULL CHECK (
                    status IN (
                        'queued',
                        'pending',
                        'info_sent',
                        'customer_retention',
                        'sale_creating',
                        'sale_created',
                        'billing_generated',
                        'billing_pdf_sent',
                        'scheduling_form_sent'
                    )
                ),
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_interaction TIMESTAMP,
                retry_count      INTEGER NOT NULL DEFAULT 0,
                is_processing    BOOLEAN DEFAULT 0,
                action_executed  BOOLEAN DEFAULT 0
            );
            """
        )

        # Tabela de eventos de mensagem (relacionada por spa_id)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                spa_id       INTEGER NOT NULL,
                message_id   TEXT    NOT NULL,
                event_type   TEXT    NOT NULL,
                payload      TEXT    NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (spa_id)
                REFERENCES certif_pending_renewals(spa_id)
                ON UPDATE CASCADE
                ON DELETE CASCADE
            );
            """
        )

        # Tabela de mensagens pendentes (relacionada por spa_id)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                spa_id     INTEGER NOT NULL,
                payload    TEXT    NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed  BOOLEAN DEFAULT 0,
                FOREIGN KEY (spa_id)
                REFERENCES certif_pending_renewals(spa_id)
                ON UPDATE CASCADE
                ON DELETE CASCADE
            );
            """
        )

        # Tabela de fila de fluxo aguardando ticket fechado
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_flow_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                spa_id          INTEGER NOT NULL,
                contact_number  TEXT    NOT NULL,
                func_name       TEXT    NOT NULL,
                func_args       TEXT    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'waiting' CHECK (
                    status IN ('waiting', 'checking', 'started')
                ),
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked    TIMESTAMP,
                retry_count     INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (spa_id)
                    REFERENCES certif_pending_renewals(spa_id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );
            """
        )

        # Índices otimizados
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_pending_spa_id "
            "ON certif_pending_renewals (spa_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_message_events_spa ON message_events (spa_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_messages_spa ON pending_messages (spa_id);"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_message_events_id ON message_events (message_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticket_flow_spa ON ticket_flow_queue (spa_id);"
        )

        conn.commit()
