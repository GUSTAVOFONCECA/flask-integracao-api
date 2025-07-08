# app/routes/webhook_services.py

"""
Módulo para gerenciamento de webhooks e processamento de dados de CNPJ para integração com Bitrix24.
"""

import os
import hmac
import re
import json
import base64
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict
import requests
from flask import request, jsonify
from app.config import Config
from app.utils import retry_with_backoff, standardize_phone_number


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
    :raises: requests.exceptions.RequestException: Em caso de erro na requisição

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
        "\nProcessed data:\n%s\n",
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


def update_crm_item(entity_type_id: int, spa_id: int, fields: Optional[dict]) -> dict:
    url = "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.item.update"
    payload = {
        "entityTypeId": entity_type_id,
        "id": spa_id,
        "fields": fields,
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar card SPA: {str(e)}")
        return {"error": str(e)}


def update_deal_item(entity_type_id: int, deal_id: int, fields: Optional[dict]) -> dict:
    url = "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.deal.update"
    payload = {
        "entityTypeId": entity_type_id,
        "id": deal_id,
        "fields": fields,
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        logger.debug(f"Response:\n{response.json}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar card DEAL: {str(e)}")
        return {"error": str(e)}


def add_comment_crm_timeline(fields: Optional[dict]) -> dict:
    url = "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.timeline.comment.add"
    payload = {"fields": fields}

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar card DEAL: {str(e)}")
        return {"error": str(e)}


############################################################################### DIGISAC SERVICES
DIGISAC_URL = "https://logicassessoria.digisac.chat"
DIGISAC_BASE_API = f"{DIGISAC_URL}/api/v1"
DIGISAC_CLIENT_ID = "api"
DIGISAC_CLIENT_SECRET = "secret"
DIGISAC_USER = Config.DIGISAC_USER
DIGISAC_PASSWORD = Config.DIGISAC_PASSWORD
DIGISAC_TOKEN = Config.DIGISAC_TOKEN
DIGISAC_USER_ID = Config.DIGISAC_USER_ID


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
        new_tokens = get_auth_digisac()

    if "error" in new_tokens:
        raise RuntimeError(f"Falha na autenticação: {new_tokens['error']}")

    # Atualiza tokens globais
    digisac_tokens["access_token"] = new_tokens["access_token"]
    digisac_tokens["refresh_token"] = new_tokens["refresh_token"]
    digisac_tokens["expires_at"] = datetime.today() + timedelta(
        seconds=new_tokens["expires_in"] - 60
    )


def get_auth_digisac() -> dict:
    """Obtém tokens de autenticação"""
    url = f"{DIGISAC_BASE_API}/oauth/token"
    payload = {
        "grant_type": "password",
        "client_id": DIGISAC_CLIENT_ID,
        "client_secret": DIGISAC_CLIENT_SECRET,
        "username": DIGISAC_USER,
        "password": DIGISAC_PASSWORD,
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.debug("Payload\n%s\nResponse:\n%s", payload, response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Erro na autenticação: %s", str(e))
        return {"error": str(e)}


def refresh_auth_digisac(refresh_token: str) -> dict:
    """Renova tokens de acesso"""
    url = f"{DIGISAC_BASE_API}/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": DIGISAC_CLIENT_ID,
        "client_secret": DIGISAC_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    try:
        response = requests.post(url, data=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Erro no refresh: %s", str(e))
        return {"error": str(e)}


def _get_contact_id_by_number(contact_number: str) -> str | None:
    """Privado: retorna contact_id a partir do número, ou None se não existir"""
    std_number = standardize_phone_number(contact_number, debug=True)
    logger.debug(f"Buscando contact ID para número padronizado: {std_number}")

    contacts_json_path = os.path.join(
        os.getcwd(), "app", "database", "digisac", "digisac_contacts.json"
    )

    try:
        # Gera variações para números com 13 dígitos (com nono dígito)
        possible_numbers = [std_number]
        if len(std_number) == 13:
            # Versão sem nono dígito: 55 (DDI) + 62 (DDD) + 93159124 (número)
            without_ninth = std_number[:4] + std_number[5:]
            possible_numbers.append(without_ninth)
            logger.debug(f"Gerada variação sem nono dígito: {without_ninth}")

        with open(contacts_json_path, "r", encoding="utf-8") as f:
            contacts = json.load(f)

        for contact in contacts:
            contact_num = (contact.get("data") or {}).get("number") or ""
            contact_std = standardize_phone_number(contact_num, debug=False)

            if contact_std in possible_numbers:
                logger.debug(
                    f"Contato encontrado: {contact_std} => {contact.get('id')}"
                )
                return contact.get("id")

        logger.warning(f"Nenhum contato encontrado para: {std_number}")
        return None

    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.error(f"Erro ao buscar contactId: {str(e)}")
        return None


# --- Builders genéricos ---
def build_transfer_payload(
    contact_id: str, department_id: str, comments: str, user_id: str = DIGISAC_USER_ID
) -> dict:
    """Gera payload para transferência de ticket no Digisac"""
    return {
        "departmentId": department_id,
        "userId": user_id,
        "comments": comments,
        "contactId": contact_id,
    }


def build_message_payload(
    contact_id: str, department_id: str, text: str, user_id: str
) -> dict:
    """Gera payload para envio de mensagem via Digisac"""
    return {
        "contactId": contact_id,
        "ticketDepartmentId": department_id,
        "userId": user_id,
        "text": text,
        "origin": "bot",
    }


def build_pdf_payload(
    contact_id: str, pdf_content: bytes, filename: str, text: str
) -> dict:
    """Gera payload para envio de arquivo PDF via Digisac"""
    pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
    user_id = DIGISAC_USER_ID
    return {
        "contactId": contact_id,
        "userId": user_id,
        "text": text,
        "file": {"base64": pdf_base64, "mimetype": "application/pdf", "name": filename},
    }


# --- Builders específicos para Certificação Digital ---
CERT_DEPT_ID = "154521dc-71c0-4117-a697-bd978cd442aa"
CERT_TRANSFER_COMMENTS = "Chamado aberto via automação para renovação de certificado."


def build_certification_transfer(contact_number: str) -> dict:
    """Gera payload para transferência de ticket ao departamento de Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    payload = build_transfer_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        comments=CERT_TRANSFER_COMMENTS,
    )
    return transfer_ticket_digisac(payload, contact_id)


def _build_certification_message_text(
    contact_name: str, company_name: str, days_to_expire: int
) -> str:
    """Gera texto da mensagem de aviso de vencimento do certificado"""
    days = abs(days_to_expire)
    if days_to_expire >= 0:
        return (
            "*Bot*\n"
            f"Olá {contact_name}, o certificado da empresa *{company_name}* "
            f"irá expirar dentro de {days} dias.\n"
            "Deseja renovar seu certificado? (Digite a opção)\n\n"
            "Renovar\n"
            "Não_renovar"
        )
    else:
        return (
            "*Bot*\n"
            f"Olá {contact_name}, o certificado da empresa *{company_name}* "
            f"expirou há {days} dias.\n"
            "Deseja renovar seu certificado? (Digite a opção)\n\n"
            "Renovar\n"
            "Não_renovar"
        )


def build_certification_message(
    contact_number: str, contact_name: str, company_name: str, days_to_expire: int
) -> dict:
    """Gera payload de mensagem para Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    text = _build_certification_message_text(contact_name, company_name, days_to_expire)
    payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )

    return send_message_digisac(payload)


def build_billing_certification_pdf(
    contact_number: str, company_name: str, pdf_content: bytes, filename: str
) -> dict:
    """Gera payload para envio de PDF (boleto) da Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    text = f"Segue boleto para pagamento referente à emissão de certificado digital da empresa {company_name}"
    payload = build_pdf_payload(
        contact_id=contact_id,
        pdf_content=pdf_content,
        filename=filename,
        text=text,
    )

    return send_pdf_digisac(payload)


def build_form_agendamento(
    contact_number: str, company_name: str, form_link: str
) -> dict:
    """Gera payload para envio do formulário de agendamento para Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    text = (
        "*Bot*\n"
        "Segue abaixo link para agendamento de videoconferência "
        "referente à emissão do certificado digital da empresa "
        f"*{company_name}*\n\n"
        f"Link:\n{form_link}"
    )
    payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )

    return send_message_digisac(payload)


# --- Funções de envio/refatoradas ---
@retry_with_backoff(retries=3, backoff_in_seconds=2)
def transfer_ticket_digisac(payload: dict, contact_id: str) -> dict:
    """Transfere ticket no Digisac usando parâmetros genéricos"""
    url = f"{DIGISAC_BASE_API}/contacts/{contact_id}/ticket/transfer"
    try:
        response = requests.post(
            url, headers=get_auth_headers(), json=payload, timeout=60
        )
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as e:
        logger.error("[TRANSFER] Erro de requisição: %s", e)
        return {"error": str(e)}


@retry_with_backoff(retries=3, backoff_in_seconds=2)
def send_message_digisac(payload: dict) -> dict:
    """Envia mensagem automática via Digisac usando parâmetros genéricos"""
    url = f"{DIGISAC_BASE_API}/messages"
    try:
        response = requests.post(
            url, headers=get_auth_headers(), json=payload, timeout=60
        )
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as e:
        logger.error("[MSG] Erro: %s", e)
        return {"error": str(e)}


@retry_with_backoff(retries=3, backoff_in_seconds=2)
def send_pdf_digisac(payload: dict) -> dict:
    """Envia PDF via Digisac usando parâmetros genéricos"""
    url = f"{DIGISAC_BASE_API}/messages"
    try:
        response = requests.post(
            url, headers=get_auth_headers(), json=payload, timeout=60
        )
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as e:
        logger.error("[PDF] Erro: %s", e)
        return {"error": str(e)}


def _parse_response(response) -> dict:
    """Parseia resposta da API do Digisac, tratando JSON ou texto"""
    content_type = response.headers.get("Content-Type", "")
    if response.content and "application/json" in content_type:
        try:
            data = response.json()
            logger.debug("Response JSON:\n%s", data)
            return data
        except ValueError:
            logger.warning(
                "Retorno sem JSON válido. Texto recebido:\n%s", response.text
            )
            return {"status_code": response.status_code, "text": response.text}
    else:
        logger.debug(
            "Content-Type não indica JSON (%s). Texto recebido:\n%s",
            content_type,
            response.text,
        )
        return {"status_code": response.status_code, "text": response.text}
