# app/workers/token_refresh_worker.py

import time
import logging
from app.services.conta_azul.conta_azul_services import refresh_tokens_safe
from app.utils.utils import debug

logger = logging.getLogger("token_refresh_worker")

# Margem de segurança antes do vencimento (em segundos)
WORKER_INTERVAL_SECONDS = 600


@debug
def run_token_refresh():
    """
    Worker de renovação automática de token da Conta Azul.

    Executa continuamente, respeitando o tempo restante do token.
    """
    logger.info("🧪 Iniciando token_refresh_worker (check a cada %ss)", WORKER_INTERVAL_SECONDS)
    while True:
        try:
            refresh_tokens_safe()
        except Exception as e:
            logger.exception(f"❌ Erro ao renovar token: {e}")
        time.sleep(WORKER_INTERVAL_SECONDS)
