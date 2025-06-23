# app/database.py
import os
import sqlite3
from contextlib import contextmanager

# Caminho absoluto para o diretório do banco de dados
DB_DIR = os.path.join(os.getcwd(), "app", "database")
DB_PATH = os.path.join(DB_DIR, "integrations.db")


@contextmanager
def get_db_connection():
    # Garante que o diretório existe
    os.makedirs(DB_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certif_pending_renewals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_number TEXT NOT NULL UNIQUE,
                deal_type TEXT NOT NULL,
                sale_id TEXT,
                status TEXT DEFAULT 'pending' CHECK(
                    status IN (
                        'pending',
                        'sale_created',
                        'charge_generated',
                        'pdf_sent'
                    )
                ),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER NOT NULL DEFAULT 0,
                pdf_url TEXT,
                card_crm_id INTEGER NOT NULL
            );            
            """
        )
        conn.commit()
