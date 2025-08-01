# app/utils/decorators.py
"""
Decorators module following SOLID principles.
Each decorator has a single responsibility.
"""

import time
import random
import logging
import inspect
import traceback
from functools import wraps
from typing import Tuple, Type, Union
import requests
from flask import request, jsonify

logger = logging.getLogger(__name__)


class RetryDecorator:
    """
    Retry decorator following Single Responsibility Principle.
    Handles retry logic with exponential backoff.
    """

    def __init__(
        self,
        retries: int = 3,
        backoff_in_seconds: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retry_on_exceptions: Tuple[Type[Exception], ...] = (requests.exceptions.RequestException,),
    ):
        self.retries = retries
        self.backoff_in_seconds = backoff_in_seconds
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retry_on_exceptions = retry_on_exceptions

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt <= self.retries:
                try:
                    return func(*args, **kwargs)
                except self.retry_on_exceptions as e:
                    logger.warning(
                        "Erro na tentativa %d de %d para %s: %s",
                        attempt + 1,
                        self.retries + 1,
                        func.__name__,
                        e,
                    )
                    if attempt == self.retries:
                        logger.error(
                            "Todas as tentativas falharam para %s", func.__name__
                        )
                        raise
                    sleep_time = self.backoff_in_seconds * (self.backoff_factor**attempt)
                    if self.jitter:
                        sleep_time = sleep_time * (0.5 + random.random() / 2)
                    logger.info(
                        "Aguardando %.2fs antes de tentar novamente...", sleep_time
                    )
                    time.sleep(sleep_time)
                    attempt += 1
            return wrapper


class WebhookResponseDecorator:
    """
    Webhook response decorator following Single Responsibility Principle.
    Ensures HTTP 200 responses for webhook endpoints.
    """

    @staticmethod
    def respond_with_200_on_exception(f):
        """
        Decorador para rotas de webhook que garante uma resposta HTTP 200 OK
        mesmo em caso de exceções ou deduplicação.
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                response, status_code = f(*args, **kwargs)

                if status_code != 200:
                    logger.error(
                        f"A rota {request.path} retornou status {status_code}. Forçando 200 OK."
                    )
                    return (
                        jsonify({
                            "status": "error",
                            "message": (
                                "Ocorreu um erro de processamento interno ou validação, mas o webhook foi recebido. "
                                f"Detalhes: {response.get('error', response.get('message', ''))}"
                            ),
                        }),
                        200,
                    )

                return response, status_code

            except Exception as e:
                logger.exception(
                    f"Erro inesperado na rota de webhook {request.path}. Forçando resposta 200 OK."
                )
                return (
                    jsonify({
                        "status": "error",
                        "message": (
                            "Erro interno do servidor. "
                            "O webhook foi recebido, mas o processamento falhou."
                        ),
                        "error_details": str(e),
                    }),
                    200,
                )
        return decorated_function


class DebugDecorator:
    """
    Debug decorator following Single Responsibility Principle.
    Handles debug logging with truncation.
    """

    TRUNCATE_LIMIT = 300

    @staticmethod
    def truncate(value, limit=None):
        """Reduz o valor para fins de log, mantendo representação útil"""
        if limit is None:
            limit = DebugDecorator.TRUNCATE_LIMIT

        try:
            if isinstance(value, (str, bytes)):
                val = value.decode() if isinstance(value, bytes) else value
                return val[:limit] + "...[truncated]" if len(val) > limit else val

            if isinstance(value, dict):
                return {k: DebugDecorator.truncate(v, limit) for k, v in list(value.items())[:10]}
            if isinstance(value, list):
                return [DebugDecorator.truncate(v, limit) for v in value[:10]]

            return (
                str(value)[:limit] + "...[truncated]" if len(str(value)) > limit else value
            )

        except Exception:
            return f"[Unloggable object: {type(value)}]"

    @staticmethod
    def debug(func):
        """Decorator com log de entrada, retorno, caller, stack trace e truncamento."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            stack = inspect.stack()
            caller_frame = stack[2] if len(stack) > 2 else None
            caller_name = caller_frame.function if caller_frame else "desconhecido"
            caller_info = (
                f"{caller_frame.filename}:{caller_frame.lineno}" if caller_frame else "?"
            )

            safe_args = [DebugDecorator.truncate(arg) for arg in args]
            safe_kwargs = {k: DebugDecorator.truncate(v) for k, v in kwargs.items()}

            logger.debug(
                f"--> {func.__name__} called by {caller_name} ({caller_info}) "
                f"with args={safe_args}, kwargs={safe_kwargs}"
            )

            try:
                result = func(*args, **kwargs)
                safe_result = DebugDecorator.truncate(result)
                logger.debug(f"<-- {func.__name__} returned {safe_result!r}")
                return result
            except Exception:
                tb = traceback.format_exc()
                logger.error(f"Exception in {func.__name__} called by {caller_name}:\n{tb}")
                raise

        return wrapper


# Factory functions for easy usage
def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on_exceptions: Tuple[Type[Exception], ...] = (requests.exceptions.RequestException,),
):
    """Factory function for retry decorator"""
    return RetryDecorator(retries, backoff_in_seconds, backoff_factor, jitter, retry_on_exceptions)


def respond_with_200_on_exception(f):
    """Factory function for webhook response decorator"""
    return WebhookResponseDecorator.respond_with_200_on_exception(f)


def debug(f):
    """Factory function for debug decorator"""
    return DebugDecorator.debug(f)