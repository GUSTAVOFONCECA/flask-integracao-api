# app/routes/webhook_services.py

"""
Módulo para gerenciamento de webhooks e processamento de dados de CNPJ para integração com Bitrix24.
"""

import os
import hmac
import re
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict
import requests
from flask import request, jsonify
from app.config import Config

logger = logging.getLogger(__name__)


def validate_api_key(f):
    """Decorador para validação de chave API nas requisições.

    :param f: Função a ser decorada
    :type f: function
    :return: Função decorada com validação de chave API
    :rtype: function
    :raises JSONResponse: Retorna erro 401 se a chave for inválida

    .. rubric:: Exemplo de Uso

    .. code-block:: python

        @api_bp.route("/endpoint")
        @validate_api_key
        def meu_endpoint():
            return jsonify({"status": "ok"})
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if key != Config.API_KEY:
            return jsonify({"error": "Chave de API inválida"}), 401
        return f(*args, **kwargs)

    return decorated


def verify_webhook_signature(signature: str) -> bool:
    """Verifica a assinatura HMAC-SHA256 de um webhook.

    :param signature: Assinatura do cabeçalho da requisição
    :type signature: str
    :return: True se as assinaturas coincidirem, False caso contrário
    :rtype: bool
    :raises ValueError: Se ocorrer erro na geração da assinatura

    .. note::
        Requer a configuração da variável WEBHOOK_SECRET no ambiente
    """
    if not Config.BITRIX_WEBHOOK_TOKEN:
        logger.error("BITRIX_WEBHOOK_TOKEN não configurado")
        return False

    try:
        return hmac.compare_digest(Config.BITRIX_WEBHOOK_TOKEN, signature)
    except (TypeError, ValueError) as e:
        logger.error("Erro na verificação de assinatura: %s", str(e))
        logger.debug("Assinatura\n %s", signature)
        return False


def get_cnpj_receita(cnpj: str) -> Optional[Dict]:
    """Obtém dados de CNPJ da API pública da Receita WS.

    :param cnpj: CNPJ a ser consultado (formatado ou não)
    :type cnpj: str
    :return: Dados do CNPJ ou None em caso de erro
    :rtype: dict or None
    :raises requests.exceptions.RequestException: Em caso de erro na requisição

    .. rubric:: Exemplo de Retorno

    .. code-block:: json

        {
            "estabelecimento": {
                "cnpj": "33380510000190",
                "nome_fantasia": "EMPRESA EXEMPLO",
                ...
            }
        }
    """
    cnpj_int = re.sub(r"[\.\/-]", "", str(cnpj))
    url = f"https://publica.cnpj.ws/cnpj/{cnpj_int}"

    try:
        response = requests.get(url=url, timeout=60)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            logger.error("Erro na API: %s", json.dumps(data["error"], indent=2))
            return None

        logger.info("Dados CNPJ %s obtidos com sucesso", cnpj)
        logger.debug("\nPayload:\n%s", json.dumps(data, indent=2, ensure_ascii=False))
        return data

    except requests.exceptions.RequestException as e:
        logger.error("Falha na requisição: %s", str(e))
        return None


def _safe_get(data: Dict, key: str, default: str = "") -> str:
    """Obtém valor de dicionário com tratamento seguro.

    :param data: Dicionário de origem
    :type data: dict
    :param key: Chave a ser buscada
    :type key: str
    :param default: Valor padrão caso a chave não exista, defaults to ""
    :type default: str, optional
    :return: Valor formatado como string ou valor padrão
    :rtype: str
    """
    value = data.get(key)
    return str(value).strip() if value is not None else default


def update_company_process_cnpj(raw_cnpj_json: Dict, id_empresa: str) -> Dict:
    """Processa dados de CNPJ para formato compatível com Bitrix24.

    :param raw_cnpj_json: Dados brutos da API da Receita
    :type raw_cnpj_json: dict
    :param id_empresa: ID da empresa no sistema Bitrix24
    :type id_empresa: str
    :return: Dados processados no formato do Bitrix24
    :rtype: dict

    .. rubric:: Estrutura do Retorno

    .. code-block:: python

        {
            "id": "123",
            "fields": {
                "UF_CRM_1708977581412": "33.380.510/0001-90",
                "TITLE": "RAZÃO SOCIAL",
                ...
            }
        }
    """
    company = raw_cnpj_json.get("estabelecimento", {})

    # Processamento de dados
    endereco = ", ".join(
        filter(
            None,
            [
                f"{_safe_get(company, 'tipo_logradouro')} {_safe_get(company, 'logradouro')}",
                (
                    f"N° {_safe_get(company, 'numero')}"
                    if _safe_get(company, "numero")
                    else ""
                ),
                (
                    re.sub(r"\s{2,}", " ", _safe_get(company, "complemento")).strip()
                    if _safe_get(company, "complemento")
                    else ""
                ),
            ],
        )
    ).strip(", ")

    # Formatação de campos específicos
    cnpj_formatado = re.sub(
        r"(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})",
        r"\1.\2.\3/\4-\5",
        _safe_get(company, "cnpj"),
    )

    processed_data = {
        "id": str(id_empresa),
        "fields": {
            "UF_CRM_1708977581412": cnpj_formatado,
            "TITLE": _safe_get(raw_cnpj_json, "razao_social"),
            "UF_CRM_1709838249844": _safe_get(company, "nome_fantasia"),
            "ADDRESS": endereco,
            "ADDRESS_REGION": _safe_get(company, "bairro"),
            "ADDRESS_CITY": company.get("cidade", {}).get("nome", ""),
            "ADDRESS_PROVINCE": company.get("estado", {}).get("nome", ""),
            "ADDRESS_POSTAL_CODE": re.sub(
                r"(\d{5})(\d{3})", r"\1-\2", _safe_get(company, "cep")
            ),
            "UF_CRM_1710938520402": next(
                (
                    _safe_get(insc, "inscricao_estadual")
                    for insc in company.get("inscricoes_estaduais", [])[:1]
                ),
                "Não Contribuinte",
            ),
            "UF_CRM_1720974662288": "Y",
        },
        "params": {"REGISTER_SONET_EVENT": "N"},
    }

    logger.debug(
        "\n✅ Processed data:\n%s\n",
        json.dumps(processed_data, indent=2, ensure_ascii=False),
    )

    return processed_data


def post_destination_api(processed_data: Dict, api_url: str) -> Dict:
    """Envia dados processados para API de destino.

    :param processed_data: Dados processados para envio
    :type processed_data: dict
    :param api_url: URL da API de destino
    :type api_url: str
    :return: Resposta da API com status e conteúdo
    :rtype: dict

    :raises requests.exceptions.RequestException: Em caso de erro na requisição

    .. rubric:: Exemplo de Resposta

    .. code-block:: python

        {
            "status_code": 200,
            "headers": {...},
            "content": {...}
        }
    """
    try:
        response = requests.post(api_url, json=processed_data, timeout=10)
        response.raise_for_status()

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.json(),
        }

    except requests.exceptions.JSONDecodeError:
        logger.warning("Resposta não é JSON válido")
        return {"content": response.text} if response else {"error": "Sem resposta"}

    except requests.exceptions.RequestException as e:
        logger.error("Erro na requisição: %s", str(e))
        return {"error": str(e)}


###############################################################################
URL_DIGISAC = "https://logicassessoria.digisac.chat"
BASE_API = f"{URL_DIGISAC}/api/v1"
CLIENT_ID = "api"
CLIENT_SECRET = "secret"


# Variável global para armazenamento de tokens
digisac_tokens = {"access_token": None, "refresh_token": None, "expires_at": None}


def get_auth_headers():
    """Retorna headers de autenticação com token válido"""
    # Verifica se o token precisa ser renovado
    if not digisac_tokens["access_token"] or (
        digisac_tokens["expires_at"]
        and datetime.utcnow() > digisac_tokens["expires_at"]
    ):
        refresh_tokens()

    return {
        "Authorization": f"Bearer {digisac_tokens['access_token']}",
        "Content-Type": "application/json",
    }


def refresh_tokens():
    """Atualiza tokens usando refresh token ou credenciais"""
    if digisac_tokens["refresh_token"]:
        new_tokens = refresh_auth_digisac(digisac_tokens["refresh_token"])
    else:
        username = Config.DIGISAC_USER
        password = Config.DIGISAC_PASSWORD
        new_tokens = get_auth_digisac(username, password)

    if "error" in new_tokens:
        raise RuntimeError(f"Falha na autenticação: {new_tokens['error']}")

    # Atualiza tokens globais
    digisac_tokens["access_token"] = new_tokens["access_token"]
    digisac_tokens["refresh_token"] = new_tokens["refresh_token"]
    digisac_tokens["expires_at"] = datetime.today() + timedelta(
        seconds=new_tokens["expires_in"] - 60
    )


def get_auth_digisac(username: str, password: str) -> dict:
    """Obtém tokens de autenticação"""
    url = f"{URL_DIGISAC}/api/v1/oauth/token"
    payload = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": username,
        "password": password,
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("❌ Erro na autenticação: %s", str(e))
        return {"error": str(e)}


def refresh_auth_digisac(refresh_token: str) -> dict:
    """Renova tokens de acesso"""
    url = f"{URL_DIGISAC}/api/v1/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("❌ Erro no refresh: %s", str(e))
        return {"error": str(e)}


def get_contact_id_by_number(contact_number: str) -> str | None:
    """
    Busca o contactId no JSON de contatos pelo número de telefone,
    considerando a possível presença do nono dígito.

    :param contact_number: Número do contato no formato recebido (ex: "Trabalho:  5562993159124")
    :return: contactId ou None se não encontrar
    """
    # Caminho para o arquivo JSON
    contacts_json_path = os.path.join(
        os.getcwd(), "app", "database", "digisac", "digisac_contacts.json"
    )

    try:
        # 1. Extrair apenas dígitos do número recebido
        raw_digits = re.sub(r"\D", "", contact_number)

        # 2. Gerar versões alternativas do número
        possible_numbers = [raw_digits]

        # Se tiver 13 dígitos (com nono dígito), criar versão sem o 9º
        if len(raw_digits) == 13:
            # Formato: 55 (DDI) + 62 (DDD) + 9 (nono) + 93159124 (número)
            # Versão sem nono dígito: 55 + 62 + 93159124 → 556293159124
            without_ninth = raw_digits[:4] + raw_digits[5:]
            possible_numbers.append(without_ninth)

        # 3. Carregar contatos do JSON
        with open(contacts_json_path, "r", encoding="utf-8") as f:
            contacts = json.load(f)

        # 4. Buscar correspondência
        for contact in contacts:
            contact_num = (contact.get("data") or {}).get("number") or ""
            contact_digits = re.sub(r"\D", "", contact_num)

            if contact_digits in possible_numbers:
                return contact.get("id")

        return None

    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.error("❌ Erro ao buscar contactId: %s", str(e))
        return None


def transfer_ticket_digisac(contact_id: str) -> dict:
    """Transfere ticket no Digisac"""
    user_id = Config.DIGISAC_USER_ID
    # ID do departamento fixo certificação digital
    department_id = "154521dc-71c0-4117-a697-bd978cd442aa"

    # Comentário da abertura do chamado
    comments = "Chamado aberto via automação para renovação de certificado."

    url = f"{BASE_API}/contacts/{contact_id}/ticket/transfer"
    payload = {"departmentId": department_id, "userId": user_id, "comments": comments}

    try:
        resp = requests.post(url, headers=get_auth_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        if resp.content and "application/json" in resp.headers.get("Content-Type", ""):
            return resp.json()
        else:
            return {"status_code": resp.status_code, "text": resp.text}

    except requests.RequestException as e:
        logger.error("❌ [TRANSFER] Erro: %s", e)
        return {"error": str(e)}


# REFATORAR CÓDIGO PARA SER MAIS GENERALISTA, RECEBENDO MSG TEXT E DEPARTMENT ID
def send_message_digisac(
    contact_id: str,
    contact_name: str,
    company_name: str,
    days_to_expire: str,
) -> dict:
    """Envia mensagem automática via Digisac"""
    user_id = Config.DIGISAC_USER_ID
    # ID do departamento fixo certificação digital
    department_id = "154521dc-71c0-4117-a697-bd978cd442aa"

    url = f"{BASE_API}/messages"
    payload = {
        "text": (
            f"Olá {contact_name}, o certificado da empresa {company_name} "
            f"irá expirar dentro de {abs(int(days_to_expire))} dias.\n"
            "Deseja renovar seu certificado? (Digite a opção)\n\n"
            "1 - Sim\n"
            "2 - Não"
        ),
        "contactId": contact_id,
        "userId": user_id,
        "ticketDepartmentId": department_id,
        "origin": "bot",
    }

    try:
        resp = requests.post(url, headers=get_auth_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("❌ [MSG] Erro: %s", e)
        return {"error": str(e)}

###############################################################################
