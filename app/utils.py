# app/utils.py

import time
import functools
import random
import logging
import requests

logger = logging.getLogger(__name__)

def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on_exceptions: tuple = (requests.exceptions.RequestException,)
):
    """
    Decorador para retry com backoff exponencial.

    :param retries: Número máximo de tentativas
    :param backoff_in_seconds: Tempo base de espera entre tentativas
    :param backoff_factor: Fator multiplicador do backoff
    :param jitter: Se True, adiciona aleatoriedade ao backoff
    :param retry_on_exceptions: Tupla de exceções que devem acionar o retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt <= retries:
                try:
                    return func(*args, **kwargs)
                except retry_on_exceptions as e:
                    logger.warning(
                        "Erro na tentativa %d de %d para %s: %s",
                        attempt + 1, retries + 1, func.__name__, e
                    )
                    if attempt == retries:
                        logger.error("Todas as tentativas falharam para %s", func.__name__)
                        raise
                    sleep_time = backoff_in_seconds * (backoff_factor ** attempt)
                    if jitter:
                        sleep_time = sleep_time * (0.5 + random.random() / 2)
                    logger.info("Aguardando %.2fs antes de tentar novamente...", sleep_time)
                    time.sleep(sleep_time)
                    attempt += 1
        return wrapper
    return decorator
