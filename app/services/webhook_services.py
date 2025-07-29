# app/routes/webhook_services.py

"""
Módulo para gerenciamento de webhooks e processamento de dados de CNPJ para integração com Bitrix24.
"""

import os
import hmac
import re
import unicodedata
import time
import json
import base64
import urllib.parse
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict
import requests
from flask import request, jsonify
from app.config import Config
from app.utils.utils import retry_with_backoff, standardize_phone_number, debug
from app.services.renewal_services import (
    get_pending,
    add_pending,
    insert_ticket_flow_queue,
)


logger = logging.getLogger(__name__)


class QueueingException(Exception):
    """
    Exceção usada para interromper o fluxo normal quando uma chamada
    é enfileirada em ticket_flow_queue, em vez de ser executada imediatamente.
    """

    def __init__(self, message: str):
        super().__init__(message)


def queue_if_open_ticket_route(add_pending_if_missing=False):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            payload_dict = {
                "args": request.args.to_dict(),
                "form": request.form.to_dict(),
            }
            spa_id = payload_dict.get("args").get("idSPA")
            contact_number = payload_dict.get("args").get("contactNumber")
            company_name = payload_dict.get("args").get("companyName")
            document = payload_dict.get("args").get("document")
            contact_name = payload_dict.get("args").get("contactName")
            deal_type = payload_dict.get("args").get("dealType")

            if not spa_id or not contact_number:
                logger.warning("SPA ID ou contactNumber ausente em rota protegida.")
                return view_func(*args, **kwargs)

            try:
                spa_id = int(spa_id)
            except ValueError:
                logger.error("ID de SPA inválido")
                return view_func(*args, **kwargs)

            std_number = standardize_phone_number(contact_number)

            if add_pending_if_missing:
                pending = get_pending(spa_id=spa_id)
                if not pending:
                    add_pending(
                        company_name=company_name,
                        document=document,
                        contact_number=std_number,
                        contact_name=contact_name,
                        deal_type=deal_type,
                        spa_id=spa_id,
                        status="pending",
                    )
                    logger.info(f"Pendência criada via decorator para SPA {spa_id}")

            if has_open_ticket_for_user_in_cert_dept(std_number):
                logger.info(
                    f"SPA {spa_id} está com ticket aberto. Enfileirando rota: {view_func.__name__}"
                )
                insert_ticket_flow_queue(
                    spa_id=spa_id,
                    contact_number=std_number,
                    func_name=view_func.__name__,
                    func_args=json.dumps(payload_dict, ensure_ascii=False),
                )
                return (
                    jsonify(
                        {
                            "status": "queued",
                            "spa_id": spa_id,
                            "message": f"Fluxo enfileirado para {view_func.__name__} enquanto o ticket estiver aberto.",
                        }
                    ),
                    200,
                )

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


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


@debug
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


@debug
def get_crm_item(entity_type_id: int, spa_id: int) -> dict:
    url = "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.item.get"
    query = {
        "entityTypeId": entity_type_id,
        "id": spa_id,
        "useOriginalUfNames": "Y",
    }

    try:
        response = requests.get(url, params=query, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar card SPA: {str(e)}")
        return {"error": str(e)}


@debug
def get_deal_item(deal_id: int) -> dict:
    url = "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.deal.get"
    query = {"id": deal_id}

    try:
        response = requests.get(url, params=query, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar card SPA: {str(e)}")
        return {"error": str(e)}


@debug
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


@debug
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


@debug
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


@debug
def _get_contact_number_by_id(contact_id: str) -> Optional[str]:
    """Obtém o número de telefone de um contato pelo ID do Digisac"""
    contacts_json_path = os.path.join(
        os.getcwd(), "app", "database", "digisac", "digisac_contacts.json"
    )

    try:
        with open(contacts_json_path, "r", encoding="utf-8") as f:
            contacts = json.load(f)

        for contact in contacts:
            if contact.get("id") == contact_id:
                return (contact.get("data") or {}).get("number")

    except Exception as e:
        logger.error(f"Erro ao buscar contato por ID: {str(e)}")

    return None


@debug
def start_bitrix_workflow(
    template_id: int, document_id: list, parameters: dict = None
) -> dict:
    """
    Inicia um business process no Bitrix24 via REST.
    """
    url = (
        "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/bizproc.workflow.start"
    )
    payload = {
        "TEMPLATE_ID": template_id,
        "DOCUMENT_ID": document_id,
        "PARAMETERS": parameters or {},
    }
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


# --- Builders genéricos ---
@debug
def build_transfer_payload(
    contact_id: str, department_id: str, comments: str, user_id: str = None
) -> dict:
    """Gera payload para transferência de ticket no Digisac"""
    queue_payload = {
        "departmentId": department_id,
        "comments": comments,
        "contactId": contact_id,
    }
    payload = {
        "departmentId": department_id,
        "userId": user_id,
        "comments": comments,
        "contactId": contact_id,
    }

    return queue_payload if user_id is None else payload


@debug
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


@debug
def build_pdf_payload(
    contact_id: str, pdf_content: bytes, filename: str, text: str
) -> dict:
    """Gera payload para envio de arquivo PDF via Digisac"""
    pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
    user_id = DIGISAC_USER_ID
    return {
        "text": text,
        "contactId": contact_id,
        "userId": user_id,
        "file": {"base64": pdf_base64, "mimetype": "application/pdf", "name": filename},
    }


# --- Builders específicos para Certificação Digital ---
CERT_DEPT_ID = "154521dc-71c0-4117-a697-bd978cd442aa"
CERT_TRANSFER_COMMENTS = "Chamado aberto via automação para renovação de certificado."
NO_BOT_DEPT_ID = "d9fe4658-1ad6-43ba-a00e-cf0b998852c2"
NO_BOT_TRANSFER_COMMENTS = "Transferência para o grupo sem bot via automação."


@debug
def build_transfer_to_certification(
    contact_number: str, to_queue: bool = False
) -> dict:
    """Gera payload para transferência de ticket ao departamento de Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)

    queue_payload = build_transfer_payload(
        user_id=DIGISAC_USER_ID,
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        comments=CERT_TRANSFER_COMMENTS,
    )

    payload = build_transfer_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        comments=CERT_TRANSFER_COMMENTS,
    )
    return (
        transfer_ticket_digisac(payload, contact_id)
        if to_queue is False
        else transfer_ticket_digisac(queue_payload, contact_id)
    )


@debug
def build_transfer_to_group_without_bot(contact_number: str) -> dict:
    """Gera payload para transferência de ticket para grupo sem bot no Digisac"""
    contact_id = _get_contact_id_by_number(contact_number)
    payload = build_transfer_payload(
        contact_id=contact_id,
        department_id=NO_BOT_DEPT_ID,
        comments=NO_BOT_TRANSFER_COMMENTS,
    )
    return transfer_ticket_digisac(payload, contact_id)


@debug
def build_certification_message(
    contact_number: str,
    contact_name: str,
    company_name: str,
    days_to_expire: int,
    deal_type: str,
) -> dict:
    """Gera payload de mensagem para Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    text = _build_certification_message_text(
        contact_name, company_name, days_to_expire, deal_type
    )
    payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )

    return send_message_digisac(payload)


@debug
def build_proposal_certification_pdf(
    contact_number: str, pdf_content: bytes, filename: str
) -> dict:
    """Gera payload para envio de proposta comercial (PDF) da Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)
    payload = build_pdf_payload(
        contact_id=contact_id,
        pdf_content=pdf_content,
        filename=filename,
        text="Proposta",
    )
    return payload


@debug
def build_send_billing_message(contact_number: str, company_name: str) -> dict:
    """Gera payload e envia mensagem de aviso sobre envio de cobrança após registro de remessa no banco"""
    contact_id = _get_contact_id_by_number(contact_number)
    text = (
        "*Bot*\n"
        "A cobrança referente a emissão de certificado digital "
        f"para *{company_name}* está sendo gerada.\n"
        "A mesma será enviada no *próximo dia útil*, após registro da cobrança no banco."
    )
    payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )

    return send_message_digisac(payload)


@debug
def send_proposal_file(
    contact_number: str,
    company_name: str,
    spa_id: int,
    filename: str = "Proposta_certificado_digital_-_Logic_Assessoria_Empresarial.pdf",
) -> dict:
    """Envia proposta de renovação via Digisac, buscando o PDF salvo como documento no CRM."""
    doc_id = [
        "crm",
        "Bitrix\\Crm\\Integration\\BizProc\\Document\\Dynamic",
        f"DYNAMIC_137_{spa_id}",
    ]

    # Mensagem inicial informando geração da proposta
    contact_id = _get_contact_id_by_number(contact_number)
    init_text = "*Bot*\n" "Sua proposta está sendo gerada e será enviada em instantes."
    init_payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=init_text,
        user_id=DIGISAC_USER_ID,
    )
    send_message_digisac(init_payload)

    # Inicia workflow para gerar documentação atualizada
    logger.info("Iniciando workflow Bitrix para geração de proposta.")
    start_bitrix_workflow(template_id=556, document_id=doc_id)
    time.sleep(45)

    # Busca o card no CRM e obtém URL do PDF, aguardando até estar disponível
    max_retries = 6
    retries = 0
    while True:
        crm = get_crm_item(entity_type_id=137, spa_id=spa_id)
        doc_info = crm.get("result", {}).get("item", {}).get("UF_CRM_18_1752245366")
        if doc_info and isinstance(doc_info, dict) and "urlMachine" in doc_info:
            break
        retries += 1
        if retries >= max_retries:
            error_text = (
                "*Bot*\n"
                "Não foi possível gerar a proposta no momento. "
                "Por favor, tente novamente mais tarde."
            )
            error_payload = build_message_payload(
                contact_id=contact_id,
                department_id=CERT_DEPT_ID,
                text=error_text,
                user_id=DIGISAC_USER_ID,
            )
            send_message_digisac(error_payload)
            logger.error(
                f"Limite de tentativas ({max_retries}) excedido ao buscar proposta."
            )
            return {"error": "Limite de tentativas excedido ao buscar proposta."}
        logger.warning(
            f"Proposta não disponível ainda (tentativa {retries}), aguardando 30s para nova verificação."
        )
        time.sleep(30)

    # Baixa o PDF via urlMachine
    try:
        response = requests.get(doc_info["urlMachine"], timeout=60)
        response.raise_for_status()
        pdf_bytes = response.content
    except Exception as e:
        logger.exception("Erro ao baixar PDF do Bitrix")
        return {"error": f"Erro ao baixar PDF: {e}"}

    # Envia o PDF via Digisac
    pdf_payload = build_proposal_certification_pdf(
        contact_number=contact_number,
        pdf_content=pdf_bytes,
        filename=filename,
    )
    pdf_response = send_pdf_digisac(pdf_payload)

    # Mensagem final de entrega da proposta
    final_text = (
        "*Bot*\n"
        "Olá! Segue a proposta comercial para renovação do "
        f"certificado digital da empresa *{company_name}*.\n"
        "Qualquer dúvida, estamos à disposição."
    )
    final_payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=final_text,
        user_id=DIGISAC_USER_ID,
    )
    send_message_digisac(final_payload)

    return pdf_response


@debug
def build_billing_certification_pdf(
    contact_number: str, company_name: str, deal_id: int, filename: str
) -> dict:
    """
    Gera e envia o PDF de cobrança, aguardando a URL no CRM.
    A lógica foi simplificada para esperar uma URL direta do Conta Azul.
    """
    max_retries = 6
    retries = 0
    doc_url = None

    while retries < max_retries:
        deal = get_deal_item(deal_id=deal_id)
        # Espera-se que o campo contenha a URL como uma string direta.
        doc_info_url = deal.get("result", {}).get("UF_CRM_1751478607")

        # Validação simplificada: verifica se é uma string e se é do domínio esperado.
        if isinstance(doc_info_url, str) and doc_info_url.startswith(
            "https://public.contaazul.com"
        ):
            doc_url = doc_info_url
            logger.info(
                f"URL de cobrança do Conta Azul encontrada para o Deal ID: {deal_id}"
            )
            break  # Sai do loop, pois a URL foi encontrada e validada.

        retries += 1
        logger.warning(
            f"URL de cobrança não encontrada para o Deal ID {deal_id} (tentativa {retries}/{max_retries}). Aguardando 30s."
        )
        time.sleep(30)

    # Se o loop terminar sem encontrar a URL, retorna um erro.
    if not doc_url:
        logger.error(
            f"Limite de tentativas excedido. URL de cobrança não encontrada para o Deal ID: {deal_id}."
        )
        return {"error": "Limite de tentativas excedido ao buscar URL da cobrança."}

    # O restante da função para baixar o PDF e enviar via Digisac continua igual.
    try:
        response = requests.get(doc_url, timeout=60)
        response.raise_for_status()
        pdf_bytes = response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao baixar o PDF da cobrança da URL: {doc_url}. Erro: {e}")
        return {"error": f"Falha ao baixar o PDF da cobrança: {e}"}

    contact_id = _get_contact_id_by_number(contact_number)

    # Envia mensagem de texto inicial
    text = (
        "*Bot*\n"
        "Segue boleto para pagamento referente à emissão "
        f"de certificado digital da empresa *{company_name}*."
    )
    message_payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )
    send_message_digisac(message_payload)

    # Gera payload e envia o PDF via Digisac
    payload = build_pdf_payload(
        contact_id=contact_id,
        pdf_content=pdf_bytes,
        filename=filename,
        text="Cobrança",
    )
    return send_pdf_digisac(payload)


@debug
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
    message_response = send_message_digisac(payload)
    return message_response


# --- Funções de envio/refatoradas ---
@debug
@retry_with_backoff(retries=3, backoff_in_seconds=2)
def fetch_open_ticket_for_user(contact_number: str) -> bool:
    """Verifica se há chamado aberto para o cliente"""
    contact_id = _get_contact_id_by_number(contact_number)
    query = {
        "where": {"isOpen": True},
        "include": [
            {
                "model": "contact",
                "required": True,
                "where": {"visible": True, "id": contact_id},
            }
        ],
    }

    encoded_query = urllib.parse.quote(json.dumps(query))
    url = f"{DIGISAC_BASE_API}/tickets?query={encoded_query}"

    resp = requests.get(url, headers=get_auth_headers())
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data", []) or []
    return items[0] if items else None


def has_open_ticket_for_user_in_cert_dept(contact_number: str) -> bool:
    """
    Retorna True se existir um ticket aberto EM OUTRO departamento
    (i.e. distinto do CERT_DEPT_ID);
    se o único aberto for no CERT_DEPT_ID, retorna False.
    """
    ticket = fetch_open_ticket_for_user(contact_number)
    if not ticket:
        return False
    # Se o ticket estiver NO SEU departamento, deixamos passar:
    return ticket.get("departmentId") != CERT_DEPT_ID


@debug
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


@debug
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


@debug
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


@debug
@retry_with_backoff(retries=3, backoff_in_seconds=2)
def close_ticket_digisac(contact_number: str) -> dict:
    """Encerra o ticket do contato no Digisac"""
    contact_id = _get_contact_id_by_number(contact_number)
    url = f"{DIGISAC_BASE_API}/contacts/{contact_id}/ticket/close"
    try:
        response = requests.post(url, headers=get_auth_headers(), timeout=60)
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as e:
        logger.error("[CLOSE] Erro ao encerrar o ticket: %s", e)
        return {"error": str(e)}


@debug
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


@debug
def _build_certification_message_text(
    contact_name: str, company_name: str, days_to_expire: int, deal_type: str
) -> str:
    """
    Gera texto da mensagem de aviso de vencimento do
    certificado com comandos claros e específicos
    """
    days = abs(days_to_expire)
    validade_msg = (
        f"*IRÁ EXPIRAR EM {days} DIAS.*"
        if days_to_expire >= 0
        else f"*EXPIROU HÁ {days} DIAS.*"
    )

    pf_msg = (
        "*Bot*\n"
        f"Olá {contact_name}, o certificado da empresa *{company_name}* {validade_msg}\n"
        f"O valor para emissão é de *R$ 185,00.*\n\n"
        "Escolha uma das opções abaixo, digitando *exatamente* a palavra:\n\n"
        "✅ Digite: *RENOVAR* → Iniciar o processo de emissão\n"
        "ℹ️ Digite: *INFO* → Falar com um atendente para mais informações\n"
        "❌ Digite: *RECUSAR* → Não deseja renovar o certificado no momento"
    )

    pj_msg = (
        "*Bot*\n"
        f"Olá {contact_name}, o certificado de Pessoa Fisica *{company_name}* {validade_msg}\n"
        f"O valor para emissão é de *R$ 130,00.*\n\n"
        "Escolha uma das opções abaixo, digitando *exatamente* a palavra:\n\n"
        "✅ Digite: *RENOVAR* → Iniciar o processo de emissão\n"
        "ℹ️ Digite: *INFO* → Falar com um atendente para mais informações\n"
        "❌ Digite: *RECUSAR* → Não deseja renovar o certificado no momento"
    )

    return pj_msg if deal_type == "Pessoa jurídica" else pf_msg


@debug
def sanitize_user_input(user_input: str) -> str:
    return (
        unicodedata.normalize("NFKD", user_input)
        .encode("ASCII", "ignore")
        .decode("utf-8")
        .strip()
        .upper()
    )


@debug
def interpret_certification_response(text: str) -> str:
    """Interpreta o texto do usuário sanitizado para mapear ações específicas"""
    text_clean = sanitize_user_input(text)

    if text_clean == "RENOVAR":
        return "renew"
    if text_clean == "INFO":
        return "info"
    if text_clean == "RECUSAR":
        return "refuse"
    return "unknown"


@debug
def send_processing_notification(contact_number: str):
    """Envia notificação para aguardar processamento"""
    contact_id = _get_contact_id_by_number(contact_number)
    if not contact_id:
        logger.warning(f"Contato não encontrado: {contact_number}")
        return None

    text = (
        "*Bot*\n"
        "⏳ Estamos processando sua solicitação anterior!\n\n"
        "• Aguarde até receber confirmação\n"
        "• Não envie novos comandos agora\n"
        "• Responderei assim que estiver pronto"
    )

    payload = build_message_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        text=text,
        user_id=DIGISAC_USER_ID,
    )
    return send_message_digisac(payload)
