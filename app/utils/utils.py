# app/utils.py

import datetime
import os
import re
import time
import random
import logging
import inspect
import traceback
from functools import wraps
import requests
from flask import request, jsonify
from selenium.webdriver.common.by import By


logger = logging.getLogger(__name__)


def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on_exceptions: tuple = (requests.exceptions.RequestException,),
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
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt <= retries:
                try:
                    return func(*args, **kwargs)
                except retry_on_exceptions as e:
                    logger.warning(
                        "Erro na tentativa %d de %d para %s: %s",
                        attempt + 1,
                        retries + 1,
                        func.__name__,
                        e,
                    )
                    if attempt == retries:
                        logger.error(
                            "Todas as tentativas falharam para %s", func.__name__
                        )
                        raise
                    sleep_time = backoff_in_seconds * (backoff_factor**attempt)
                    if jitter:
                        sleep_time = sleep_time * (0.5 + random.random() / 2)
                    logger.info(
                        "Aguardando %.2fs antes de tentar novamente...", sleep_time
                    )
                    time.sleep(sleep_time)
                    attempt += 1

        return wrapper

    return decorator


def respond_with_200_on_exception(f):
    """
    Decorador para rotas de webhook que garante uma resposta HTTP 200 OK
    mesmo em caso de exceções ou deduplicação.

    Captura exceções, registra o erro, e retorna um JSON com status de erro
    mas com HTTP 200 para evitar reenvios do webhook.
    Também garante 200 OK para eventos duplicados/ignorados.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Tenta executar a função da rota
            response, status_code = f(*args, **kwargs)

            # Se a resposta já for 200 OK, apenas a retorna.
            # Se for outro status (ex: 403 por assinatura inválida),
            # ainda assim, vamos retornar 200 e logar a falha de autenticação.
            if status_code != 200:
                logger.error(
                    f"A rota {request.path} retornou status {status_code}. Forçando 200 OK."
                )
                # Modifica o status para 200, mas mantém o conteúdo da resposta original.
                # Ou, se preferir uma mensagem mais genérica para erros não-200:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Ocorreu um erro de processamento interno ou validação, mas o webhook foi recebido. Detalhes: {response.get('error', response.get('message', ''))}",
                        }
                    ),
                    200,
                )

            return response, status_code

        except Exception as e:
            logger.exception(
                f"Erro inesperado na rota de webhook {request.path}. Forçando resposta 200 OK."
            )
            # Em caso de qualquer exceção, retorna 200 OK para o sistema de origem
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Erro interno do servidor. O webhook foi recebido, mas o processamento falhou.",
                        "error_details": str(
                            e
                        ),  # Opcional: incluir detalhes para debug (cuidado em produção)
                    }
                ),
                200,
            )

    return decorated_function


TRUNCATE_LIMIT = 300  # Limite de caracteres por valor logado


def truncate(value, limit=TRUNCATE_LIMIT):
    """Reduz o valor para fins de log, mantendo representação útil"""
    try:
        # Se for string ou bytes
        if isinstance(value, (str, bytes)):
            val = value.decode() if isinstance(value, bytes) else value
            return val[:limit] + "...[truncated]" if len(val) > limit else val

        # Se for dicionário ou lista, aplica truncamento recursivo
        if isinstance(value, dict):
            return {k: truncate(v, limit) for k, v in list(value.items())[:10]}
        if isinstance(value, list):
            return [truncate(v, limit) for v in value[:10]]

        # Qualquer outro tipo, tenta representação direta
        return (
            str(value)[:limit] + "...[truncated]" if len(str(value)) > limit else value
        )

    except Exception:
        return f"[Unloggable object: {type(value)}]"


def debug(func):
    """Decorator com log de entrada, retorno, caller, stack trace e truncamento."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Descobre quem chamou esta função
        stack = inspect.stack()
        caller_frame = stack[2] if len(stack) > 2 else None
        caller_name = caller_frame.function if caller_frame else "desconhecido"
        caller_info = (
            f"{caller_frame.filename}:{caller_frame.lineno}" if caller_frame else "?"
        )

        # Truncar argumentos para o log
        safe_args = [truncate(arg) for arg in args]
        safe_kwargs = {k: truncate(v) for k, v in kwargs.items()}

        # Log de entrada
        logger.debug(
            f"--> {func.__name__} called by {caller_name} ({caller_info}) "
            f"with args={safe_args}, kwargs={safe_kwargs}"
        )

        try:
            result = func(*args, **kwargs)
            safe_result = truncate(result)
            logger.debug(f"<- {func.__name__} returned {safe_result!r}")
            return result
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Exception in {func.__name__} called by {caller_name}:\n{tb}")
            raise

    return wrapper


def save_page_diagnosis(driver, exception, filename_prefix="element_error"):
    """Salva diagnóstico completo da página quando ocorre falha com elementos"""
    # Criar diretório de logs se não existir
    log_dir = "selenium_diagnostics"
    os.makedirs(log_dir, exist_ok=True)

    # Nome do arquivo com timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{log_dir}/{filename_prefix}_{timestamp}"

    # Salvar screenshot
    driver.save_screenshot(f"{filename}.png")

    # Salvar HTML da página
    with open(f"{filename}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    # Coletar informações de elementos
    element_info = []

    # Informações básicas da página
    element_info.append("=" * 80)
    element_info.append(f"Diagnóstico da Página - {timestamp}")
    element_info.append("=" * 80)
    element_info.append(f"URL: {driver.current_url}")
    element_info.append(f"Título: {driver.title}")
    element_info.append(f"Exceção: {type(exception).__name__}: {str(exception)}")
    element_info.append("\n" + "=" * 80)
    element_info.append("ESTADO DOS ELEMENTOS-CHAVE")
    element_info.append("=" * 80)

    # Verificar elementos importantes
    key_elements = {
        "username_field": "input[name='username']",
        "password_field": "input[name='password']",
        "submit_button": "input[name='signInSubmitButton']",
        "login_form": "form[name='cognitoSignInForm']",
        "iframe": "iframe",
        "local_tunnel_warning": "#tunnel-password-input",
    }

    for name, selector in key_elements.items():
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            element_info.append(f"{name.upper()} ({selector})")
            element_info.append(f"  Encontrados: {len(elements)} elementos")

            for i, element in enumerate(elements, 1):
                state = []
                try:
                    state.append(
                        f"Visível: {'Sim' if element.is_displayed() else 'Não'}"
                    )
                    state.append(
                        f"Habilitado: {'Sim' if element.is_enabled() else 'Não'}"
                    )
                    state.append(
                        f"Texto: {element.text[:50] + '...' if element.text else 'N/A'}"
                    )
                    state.append(
                        f"Valor: {element.get_attribute('value')[:50] + '...' if element.get_attribute('value') else 'N/A'}"
                    )
                except Exception as e:
                    state.append(f"Erro ao verificar estado: {str(e)}")

                element_info.append(f"  Elemento {i}:")
                element_info.extend([f"    {s}" for s in state])

        except Exception as e:
            element_info.append(f"ERRO ao verificar {name}: {str(e)}")

    # Informações gerais sobre a página
    element_info.append("\n" + "=" * 80)
    element_info.append("ESTRUTURA GERAL DA PÁGINA")
    element_info.append("=" * 80)

    try:
        # Contagem de elementos por tipo
        element_counts = {
            "formulários": "form",
            "inputs": "input",
            "botões": "button",
            "iframes": "iframe",
            "divs": "div",
        }

        for desc, selector in element_counts.items():
            count = len(driver.find_elements(By.CSS_SELECTOR, selector))
            element_info.append(f"{desc.capitalize()}: {count}")

        # Estrutura de títulos
        element_info.append("\nCabeçalhos:")
        for level in range(1, 7):
            headers = driver.find_elements(By.CSS_SELECTOR, f"h{level}")
            element_info.append(f"  H{level}: {len(headers)} encontrados")

    except Exception as e:
        element_info.append(f"Erro ao analisar estrutura: {str(e)}")

    # Salvar diagnóstico em TXT
    with open(f"{filename}.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(element_info))

    return filename


def standardize_phone_number(phone: str, debug: bool = False) -> str | None:
    """
    Padroniza números de telefone brasileiros para formato internacional completo (DDI + DDD + número)

    :param phone: Número de telefone em qualquer formato
    :param debug: Habilita logs de warning para números inválidos
    :return: Número padronizado (ex: 5562993159124) ou None se inválido
    """
    if not phone or not isinstance(phone, str):
        return None

    # Remove todos os não-dígitos
    digits = re.sub(r"\D", "", phone)
    n = len(digits)

    # Verificação de comprimento válido
    if n < 10 or n > 13:
        if debug:
            logger.warning(
                f"Comprimento inválido para telefone brasileiro: {phone} (len={n})"
            )
        return None

    # Números com DDI (55) já completo
    if digits.startswith("55") and n in (12, 13):
        return digits

    # Números sem DDI mas com DDD (10 ou 11 dígitos)
    if n in (10, 11):
        return "55" + digits

    # Tratamento especial para números de 9 dígitos (sem DDD/DDI)
    if n == 9:
        # Assume DDI 55 e DDD padrão 62 (Goiás)
        return "5562" + digits

    if debug:
        logger.warning(f"Formato não suportado: {phone} (len={n})")
    return None
