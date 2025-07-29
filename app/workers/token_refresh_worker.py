# app/workers/token_refresh_worker.py

import time
import logging
from app.services.conta_azul.conta_azul_services import (
    get_token_expiry_delay,
    auto_authenticate,
    refresh_tokens,
    set_tokens,
)
from app.utils.utils import debug

logger = logging.getLogger("token_refresh_worker")

# Margem de segurança antes do vencimento (em segundos)
SAFETY_MARGIN_SECONDS = 60


@debug
def refresh_if_needed():
    """
    Verifica o tempo restante do token e realiza a renovação se necessário.

    Retorna:
        float: tempo (em segundos) até a próxima execução do worker.
    """
    delay = get_token_expiry_delay()

    if delay is None:
        logger.warning("❗ Token inválido ou ausente. Executando autenticação inicial...")
        auto_authenticate()
        delay = get_token_expiry_delay()

    if delay is not None:
        wait_time = max(delay - SAFETY_MARGIN_SECONDS, 5)
        logger.info(f"⏳ Aguardando {int(wait_time)}s até a próxima renovação.")
    else:
        logger.warning("⚠️ Token ainda inválido. Tentando novamente em 60s.")
        return 60

    try:
        logger.info("🔁 Renovando token da Conta Azul...")
        token_data = refresh_tokens()
        set_tokens(token_data)
        logger.info("✅ Token renovado com sucesso.")
    except Exception as e:
        logger.error(f"❌ Erro ao renovar token: {e}")
        return 60

    return wait_time


@debug
def run_token_refresh():
    """
    Worker de renovação automática de token da Conta Azul.

    Executa continuamente, respeitando o tempo restante do token.
    """
    logger.info("🔄 Token refresh worker iniciado.")
    while True:
        wait_seconds = refresh_if_needed()
        time.sleep(wait_seconds)
