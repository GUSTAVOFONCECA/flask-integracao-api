# app/workers/session_worker.py
import time
import logging
from app.services.renewal_services import (
    try_finalize_session,
    check_expired_contact_sessions,
)
from app.utils.utils import debug

# Intervalo entre verificações e tempo de expiração
WORKER_INTERVAL_SECONDS = 60
SESSION_TIMEOUT_MINUTES = 30

# Logger dedicado
logger = logging.getLogger("session_worker")


@debug
def check_expired_sessions():
    """Verifica sessões expiradas e tenta encerrá-las"""
    sessions = check_expired_contact_sessions()
    if sessions:
        logger.info(f"🔍 Verificando {len(sessions)} sessões expiradas.")

    for session in sessions:
        contact_number = session["contact_number"]
        logger.info(f"⏳ Sessão expirada para {contact_number} → tentando encerrar.")
        try_finalize_session(contact_number)

@debug
def run_session_worker():
    """Função principal do worker de sessões"""
    logger.info(
        "🔁 Iniciando loop do session worker (intervalo de %ss).",
        WORKER_INTERVAL_SECONDS,
    )
    while True:
        check_expired_sessions()
        time.sleep(WORKER_INTERVAL_SECONDS)
