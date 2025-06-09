# app/services/conta_azul_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Union
from urllib.parse import urlencode
import base64
import requests
from app.config import Config
from app.services.conta_azul_auto_auth import automate_auth


logger = logging.getLogger(__name__)

# Endpoints da Conta Azul
TOKEN_URL = "https://auth.contaazul.com/oauth2/token"
API_BASE_URL = "https://api-v2.contaazul.com"

# Armazenamento de tokens (em memória - para produção use persistência)
conta_azul_tokens: Dict[str, Optional[Union[str, datetime]]] = {
    "access_token": None,
    "refresh_token": None,
    "id_token": None,
    "expires_at": None,
}


def auto_authenticate():
    """Obtém tokens através da automação Selenium"""
    # Obter código de autorização via Selenium
    auth_code = automate_auth()

    # Trocar código por tokens
    token_data = get_tokens(auth_code)
    set_tokens(token_data)
    return token_data


def get_tokens(code: str) -> dict:
    """Troca o código de autorização por tokens de acesso."""
    # Preparar credenciais para Basic Auth
    credentials = f"{Config.CONTA_AZUL_CLIENT_ID}:{Config.CONTA_AZUL_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }

    # Dados SEM urlencode - enviar como dicionário
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": Config.CONTA_AZUL_REDIRECT_URI,
        # Remover client_id e client_secret do corpo se usar Basic Auth
    }

    # Adicionar logs detalhados
    logger.debug(f"Request data: {data}")
    logger.debug(f"Authorization: Basic {encoded_credentials[:10]}")

    response = requests.post(
        TOKEN_URL,
        data=data,  # Enviar como dicionário, não urlencode
        headers=headers,
        timeout=60
    )

    # Log completo da resposta
    logger.debug(f"Token response: {response.status_code} - {response.text}")

    if response.status_code != 200:
        logger.error(f"Erro na requisição de tokens: {response.status_code}")
        logger.error(f"Resposta completa: {response.text}")
        # Tentar extrair detalhes do erro
        try:
            error_data = response.json()
            logger.error(f"Error: {error_data.get('error')}")
            logger.error(f"Error description: {error_data.get('error_description')}")
        except:
            pass

    response.raise_for_status()
    return response.json()


def refresh_tokens() -> dict:
    """Renova os tokens de acesso usando o refresh token."""
    if not conta_azul_tokens["refresh_token"]:
        raise ValueError("Nenhum refresh token disponível")

    # Preparar credenciais para Basic Auth
    credentials = f"{Config.CONTA_AZUL_CLIENT_ID}:{Config.CONTA_AZUL_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }

    # Preparar dados com escopo e codificação adequada
    data = {
        "grant_type": "refresh_token",
        "refresh_token": conta_azul_tokens["refresh_token"],
        "client_id": Config.CONTA_AZUL_CLIENT_ID,
        "client_secret": Config.CONTA_AZUL_CLIENT_SECRET,
        "scope": "openid profile aws.cognito.signin.user.admin",
    }

    # Fazer requisição com parâmetros devidamente codificados
    response = requests.post(
        TOKEN_URL, data=urlencode(data), headers=headers, timeout=60
    )

    # Adicionar logs para debug
    if response.status_code != 200:
        logger.error(f"Erro na renovação de tokens: {response.status_code}")
        logger.error(f"Resposta: {response.text}")

    response.raise_for_status()
    return response.json()


def set_tokens(token_data: dict):
    """Armazena os tokens e calcula o tempo de expiração."""
    conta_azul_tokens["access_token"] = token_data["access_token"]
    conta_azul_tokens["refresh_token"] = token_data["refresh_token"]
    conta_azul_tokens["id_token"] = token_data.get("id_token")
    conta_azul_tokens["expires_at"] = datetime.now() + timedelta(
        seconds=token_data["expires_in"]
    )


def is_authenticated() -> bool:
    """Verifica se temos um token de acesso válido."""
    if not conta_azul_tokens["access_token"]:
        return False

    expires_at = conta_azul_tokens["expires_at"]
    # Verify that expires_at is a datetime object and not None
    if expires_at and isinstance(expires_at, datetime):
        if datetime.now() >= expires_at:
            try:
                token_data = refresh_tokens()
                set_tokens(token_data)
                return True
            except requests.exceptions.RequestException as e:
                logger.error("Falha ao renovar token: %s", e)
                return False

    return True


def get_auth_headers() -> dict:
    """Retorna os headers de autenticação."""
    if not is_authenticated():
        raise PermissionError("Não autenticado na Conta Azul")
    return {
        "Authorization": f"Bearer {conta_azul_tokens['access_token']}",
        "Content-Type": "application/json",
    }


def get_sales(page: int = 1, size: int = 100) -> dict:
    """Obtém vendas da API da Conta Azul."""
    url = f"{API_BASE_URL}/sales/v1/sales_orders"
    params = {"page": page, "size": size}

    response = requests.get(url, params=params, headers=get_auth_headers(), timeout=10)
    response.raise_for_status()
    return response.json()
