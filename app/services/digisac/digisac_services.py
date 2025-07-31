# app/services/digisac/digisac_services.py

import os
import json
import logging
import unicodedata
import time
import base64
import urllib.parse
from functools import wraps
from typing import Optional
from datetime import datetime, timedelta
import requests
from flask import request, jsonify
from app.config import Config
from app.utils.utils import retry_with_backoff, standardize_phone_number, debug
from app.services.renewal_services import (
    get_pending,
    add_pending,
    insert_ticket_flow_queue,
)
from app.services.bitrix24.bitrix_services import (
    start_bitrix_workflow,
    get_crm_item,
    get_deal_item,
)


DIGISAC_URL = "https://logicassessoria.digisac.chat"
DIGISAC_BASE_API = f"{DIGISAC_URL}/api/v1"
DIGISAC_CLIENT_ID = "api"
DIGISAC_CLIENT_SECRET = "secret"
DIGISAC_USER = Config.DIGISAC_USER
DIGISAC_PASSWORD = Config.DIGISAC_PASSWORD
DIGISAC_TOKEN = Config.DIGISAC_TOKEN
DIGISAC_USER_ID = Config.DIGISAC_USER_ID

# --- Builders específicos para Certificação Digital ---
CERT_DEPT_ID = "154521dc-71c0-4117-a697-bd978cd442aa"
CERT_TRANSFER_COMMENTS = "Chamado aberto via automação para renovação de certificado."
NO_BOT_DEPT_ID = "d9fe4658-1ad6-43ba-a00e-cf0b998852c2"
NO_BOT_TRANSFER_COMMENTS = "Transferência para o grupo sem bot via automação."


logger = logging.getLogger(__name__)


TOKENS_FILE = os.path.join("app", "database", "digisac", "digisac_tokens.json")
os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)

digisac_tokens = {"access_token": None, "refresh_token": None, "expires_at": None}


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
                            "message": (
                                f"Fluxo enfileirado para {view_func.__name__} "
                                "enquanto o ticket estiver aberto.",
                            ),
                        }
                    ),
                    200,
                )

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def get_auth_headers_digisac() -> dict:
    load_tokens()
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
    """
    Atualiza os tokens da Digisac:
      - Usa o refresh_token, se existir
      - Caso contrário, usa as credenciais de usuário
    """
    load_tokens()

    # Tenta renovar usando refresh_token
    if digisac_tokens.get("refresh_token"):
        token_data = refresh_auth_digisac(digisac_tokens["refresh_token"])
    else:
        token_data = get_auth_digisac()

    # Valida resposta
    if not token_data or "access_token" not in token_data:
        raise RuntimeError(f"Falha ao atualizar tokens Digisac: {token_data}")

    # Atualiza tokens em memória
    digisac_tokens["access_token"] = token_data["access_token"]
    digisac_tokens["refresh_token"] = token_data["refresh_token"]
    digisac_tokens["expires_at"] = datetime.utcnow() + timedelta(
        seconds=token_data["expires_in"] - 60
    )

    # Persiste no JSON
    save_tokens()


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


def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k in ("access_token", "refresh_token"):
                digisac_tokens[k] = data.get(k)
            exp = data.get("expires_at")
            digisac_tokens["expires_at"] = datetime.fromisoformat(exp) if exp else None


def save_tokens():
    data = digisac_tokens.copy()
    if isinstance(data["expires_at"], datetime):
        data["expires_at"] = data["expires_at"].isoformat()
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


@debug
def build_transfer_to_certification(
    contact_number: str, to_queue: bool = False
) -> dict:
    """Gera payload para transferência ao departamento ou usuário de Certificação Digital"""
    contact_id = _get_contact_id_by_number(contact_number)

    # Payload com user_id = envia direto ao usuário
    user_payload = build_transfer_payload(
        user_id=DIGISAC_USER_ID,
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        comments=CERT_TRANSFER_COMMENTS,
    )

    # Payload apenas com o department_id = envia para a fila
    queue_payload = build_transfer_payload(
        contact_id=contact_id,
        department_id=CERT_DEPT_ID,
        comments=CERT_TRANSFER_COMMENTS,
    )

    return (
        transfer_ticket_digisac(user_payload, contact_id)
        if not to_queue
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

    resp = requests.get(url, headers=get_auth_headers_digisac())
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
            url, headers=get_auth_headers_digisac(), json=payload, timeout=60
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
            url, headers=get_auth_headers_digisac(), json=payload, timeout=60
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
            url, headers=get_auth_headers_digisac(), json=payload, timeout=60
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
        response = requests.post(url, headers=get_auth_headers_digisac(), timeout=60)
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
        "O valor para emissão do certificado é de *R$ 185,00.*\n"
        "O valor da taxa de boleto é de *R$ 1,99.*\n"
        "*Total da cobrança: R$ 186,99*\n\n"
        "Escolha uma das opções abaixo, digitando *exatamente* a palavra:\n\n"
        "✅ Digite: *RENOVAR* → Iniciar o processo de emissão\n"
        "ℹ️ Digite: *INFO* → Falar com um atendente para mais informações\n"
        "❌ Digite: *RECUSAR* → Não deseja renovar o certificado no momento"
    )

    pj_msg = (
        "*Bot*\n"
        f"Olá {contact_name}, o certificado de Pessoa Fisica *{company_name}* {validade_msg}\n"
        "O valor para emissão do certificado é de *R$ 130,00.*\n"
        "O valor da taxa de boleto é de *R$ 1,99.*\n"
        "*Total da cobrança: R$ 131,99*\n\n"
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
