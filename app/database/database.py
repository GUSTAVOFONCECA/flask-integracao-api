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
        # 1) pendências de certificados (fluxo de negócios)
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS certif_pending_renewals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            spa_id           INTEGER NOT NULL UNIQUE,
            company_name     TEXT    NOT NULL,
            contact_number   TEXT    NOT NULL,
            deal_type        TEXT    NOT NULL,
            sale_id          TEXT,
            financial_event_id TEXT,
            status           TEXT    NOT NULL DEFAULT 'pending' CHECK (
                status IN (
                    'pending',
                    'info_sent',
                    'customer_retention',
                    'sale_created',
                    'billing_generated',
                    'billing_pdf_sent',
                    'scheduling_form_sent'
                )
            ),
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_interaction TIMESTAMP,
            is_processing    BOOLEAN DEFAULT 0,
            retry_count      INTEGER NOT NULL DEFAULT 0
        );
        """
        )

        # índice para lookup rápido por spa_id
        conn.execute(
            """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_certif_spa_id
          ON certif_pending_renewals (spa_id);
        """
        )

        # 2) eventos de mensagem para dedup + audit
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS message_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            spa_id       INTEGER NOT NULL,
            message_id   TEXT    NOT NULL,
            event_type   TEXT    NOT NULL,
            payload_hash TEXT    NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (spa_id)
              REFERENCES certif_pending_renewals(spa_id)
              ON UPDATE CASCADE
              ON DELETE CASCADE
        );
        """
        )

        # impede duplicação de message_id
        conn.execute(
            """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_message_events_message_id
         ON message_events (message_id);
        """
        )

        # índice para acelerar consultas de histórico por spa_id
        conn.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_message_events_spa
         ON message_events (spa_id);
        """
        )

        # Tabela para armazenar as mensagens pendentes e seus estados de processamento
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS pending_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_number TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT 0
        );
        """
        )

        # Índices para otimização
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_messages_contact"
            "ON pending_messages (contact_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_messages_unprocessed"
            "ON pending_messages (contact_number, processed) WHERE processed = 0"
        )

        conn.commit()
