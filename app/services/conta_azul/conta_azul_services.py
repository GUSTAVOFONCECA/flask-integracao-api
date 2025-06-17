# app/services/conta_azul_service.
import os
import json
import re
from pathlib import Path
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Union
import base64
import requests
from app.config import Config
from app.services.conta_azul.conta_azul_auto_auth import automate_auth
from app.utils import standardize_phone_number


logger = logging.getLogger(__name__)

# Endpoints da Conta Azul
TOKEN_URL = "https://auth.contaazul.com/oauth2/token"
API_BASE_URL = "https://api-v2.contaazul.com"

# Caminho do arquivo de persistência de tokens
TOKEN_FILE_PATH = os.path.join(
    os.getcwd(), "app", "database", "conta_azul", "conta_azul_tokens.json"
)


# Armazenamento de tokens (em memória - para produção use persistência)
conta_azul_tokens: Dict[str, Optional[Union[str, datetime]]] = {
    "access_token": None,
    "refresh_token": None,
    "id_token": None,
    "expires_at": None,
}


############################################################################### CONTA AZUL AUTH SERVICES
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

    # Monta a string manualmente
    body = (
        f"client_id={Config.CONTA_AZUL_CLIENT_ID}"
        f"&client_secret={Config.CONTA_AZUL_CLIENT_SECRET}"
        f"&grant_type=authorization_code"
        f"&code={code}"
        f"&redirect_uri={Config.CONTA_AZUL_REDIRECT_URI}"
    )

    # Adicionar logs detalhados
    logger.debug(f"Request data: {body}")
    logger.debug(f"Authorization: Basic {encoded_credentials}")

    response = requests.post(
        TOKEN_URL,
        data=body,  # Enviar como dicionário, não urlencode
        headers=headers,
        timeout=60,
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
    body = (
        f"client_id={Config.CONTA_AZUL_CLIENT_ID}"
        f"&client_secret={Config.CONTA_AZUL_CLIENT_SECRET}"
        f"&grant_type=refresh_token"
        f"&code={conta_azul_tokens['refresh_token']}"
    )

    # Fazer requisição com parâmetros devidamente codificados
    response = requests.post(TOKEN_URL, data=body, headers=headers, timeout=60)

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

    logger.debug("Conta azul tokens:\n%s", conta_azul_tokens)
    save_tokens_to_file()


def save_tokens_to_file():
    data = conta_azul_tokens.copy()
    if isinstance(data["expires_at"], datetime):
        data["expires_at"] = data["expires_at"].isoformat()
    os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    logger.info("Conta azul tokens salvo no arquivo: %s", TOKEN_FILE_PATH)


def load_tokens_from_file():
    if os.path.exists(TOKEN_FILE_PATH):
        with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            conta_azul_tokens["access_token"] = data.get("access_token")
            conta_azul_tokens["refresh_token"] = data.get("refresh_token")
            conta_azul_tokens["id_token"] = data.get("id_token")
            expires_at = data.get("expires_at")
            if expires_at:
                conta_azul_tokens["expires_at"] = datetime.fromisoformat(expires_at)


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


############################################################################### CONTA AZUL MATCH SERVICES
def find_person_uuid_by_phone(phone: str) -> str | None:
    # Padroniza o número para formato internacional completo
    std_number = standardize_phone_number(phone, debug=True)
    if not std_number:
        logger.warning(f"Número {phone} não pôde ser padronizado")
        return None

    # Converte para formato Conta Azul (remove DDI 55 e mantém DDD + número)
    if len(std_number) == 13:  # Formato completo: 55 + DDD + 9 dígitos
        conta_azul_number = std_number[2:]  # Remove DDI (55)
    elif len(std_number) == 12:  # Formato sem nono: 55 + DDD + 8 dígitos
        # Converte para formato com nono dígito (padrão brasileiro)
        conta_azul_number = std_number[2:4] + "9" + std_number[4:]
    else:
        logger.warning(f"Formato não suportado: {std_number} (len={len(std_number)})")
        return None

    logger.debug(f"Buscando cliente no formato Conta Azul: {conta_azul_number}")

    with open(Path("app/database/conta_azul/person.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    for person in data.get("itens", []):
        person_phone = person.get("telefone")
        if not person_phone:
            continue

        # Padroniza telefone do cliente da Conta Azul
        person_digits = re.sub(r"\D", "", person_phone)

        # Compara diretamente com o formato Conta Azul
        if person_digits == conta_azul_number:
            return person["uuid"]

    logger.warning(f"Cliente não encontrado para: {phone} -> {conta_azul_number}")
    return None


############################################################################### CONTA AZUL SALE SERVICES
def create_sale(sale_payload: dict) -> dict:
    url = f"{API_BASE_URL}/v1/venda"
    headers = get_auth_headers()

    try:
        # ADICIONAR LOG DA REQUISIÇÃO
        logger.debug(f"POST {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Payload: {sale_payload}")

        response = requests.post(url, json=sale_payload, headers=headers, timeout=60)
        response.raise_for_status()

        # LOG DA RESPOSTA
        logger.info(f"Resposta HTTP {response.status_code}")
        logger.debug(f"Conteúdo: {response.text}")

        return response.json()

    except requests.exceptions.RequestException as e:
        # LOG DETALHADO DE ERROS DE REDE
        logger.error(f"Erro na requisição: {str(e)}")
        if hasattr(e, "response") and e.response:
            logger.error(f"Resposta do erro: {e.response.text}")
        raise


def build_sale_payload(
    client_id: str,
    service_id: str,
    price: float,
    sale_date: datetime,
    due_date: datetime,
    item_description: str,
) -> dict:
    # Gerar número sequencial baseado no timestamp
    numero_venda = int(datetime.now().timestamp())

    return {
        "id_cliente": client_id,
        "numero": numero_venda,  # CAMPO OBRIGATÓRIO ADICIONADO
        "situacao": "APROVADO",
        "data_venda": sale_date.strftime("%Y-%m-%d"),
        "itens": [
            {
                "descricao": item_description,
                "quantidade": 1,
                "valor": price,
                "id": service_id,
            }
        ],
        "condicao_pagamento": {
            "tipo_pagamento": "BOLETO_BANCARIO",
            "id_conta_financeira": "efa91453-f647-4d6f-879d-312817a337fe",
            "opcao_condicao_pagamento": "À vista",
            "parcelas": [
                {
                    "data_vencimento": due_date.strftime("%Y-%m-%d"),
                    "valor": price,
                    "descricao": "Parcela única",
                }
            ],
        },
    }


def build_sale_certif_digital_params(deal_type: str) -> dict:
    base = {
        "id_service": None,
        "item_description": None,
        "price": None,
        "sale_date": datetime.now(),
        "due_date": datetime.now() + timedelta(days=5),
    }

    if deal_type == "Pessoa jurídica":
        base.update(
            {
                "id_service": "0b4f9a8b-01bb-4a89-93b3-7f56210bc75d",
                "item_description": "CERTIFICADO DIGITAL PJ",
                "price": 180,
            }
        )
    elif deal_type == "Pessoa física - CPF":
        base.update(
            {
                "id_service": "586d5eb2-23aa-47ff-8157-fd85de8b9932",
                "item_description": "CERTIFICADO DIGITAL PF",
                "price": 130,
            }
        )
    elif deal_type == "Pessoa física - CEI":
        base.update(
            {
                "id_service": "586d5eb2-23aa-47ff-8157-fd85de8b9932",
                "item_description": "CERTIFICADO DIGITAL PF",
                "price": 130,
            }
        )
    else:
        raise ValueError(f"Tipo de negócio inválido: {deal_type}")

    return base


def handle_sale_creation_certif_digital(contact_number: str, deal_type: str) -> dict:
    """
    Orquestra a criação de venda de certificado digital na Conta Azul:
    1) Encontra o cliente pelo telefone.
    2) Monta parâmetros específicos (id_service, preço, datas).
    3) Constrói payload e chama create_sale().
    """
    # 1) Localiza o UUID do cliente pela lista local (person.json)
    client_uuid = find_person_uuid_by_phone(contact_number)
    if not client_uuid:
        raise ValueError(
            f"Cliente com telefone {contact_number} não encontrado."
        )  # :contentReference[oaicite:0]{index=0}

    # 2) Prepara parâmetros (id_service, descrição, preço, datas)
    params = build_sale_certif_digital_params(
        deal_type
    )  # :contentReference[oaicite:1]{index=1}

    # 3) Monta o payload da venda
    payload = build_sale_payload(
        client_id=client_uuid,
        service_id=params["id_service"],
        price=params["price"],
        sale_date=params["sale_date"],
        due_date=params["due_date"],
        item_description=params["item_description"],
    )  # :contentReference[oaicite:2]{index=2}

    # 4) Cria a venda e retorna o resultado, que inclui URL do boleto
    sale = create_sale(payload)  # :contentReference[oaicite:3]{index=3}
    return sale


# Carrega tokens do arquivo ao inicializar
load_tokens_from_file()
