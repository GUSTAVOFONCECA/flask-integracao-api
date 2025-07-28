# app/routes/webhook_routes.py

"""Rotas de webhook para integração com Bitrix24 e validação de CNPJ."""
from datetime import datetime
import logging
import json
from flask import Blueprint, request, jsonify
from app.services.conta_azul.conta_azul_services import (
    extract_billing_info,
    handle_sale_creation_certif_digital,
)
from app.services.webhook_services import (
    verify_webhook_signature,
    add_comment_crm_timeline,
    interpret_certification_response,
    build_send_billing_message,
    build_transfer_to_certification,
    build_certification_message,
    build_form_agendamento,
    build_billing_certification_pdf,
    send_processing_notification,
    update_company_process_cnpj,
    get_cnpj_receita,
    post_destination_api,
    update_crm_item,
    update_deal_item,
    _get_contact_number_by_id,
    queue_if_open_ticket_route,
    close_ticket_digisac,
)
from app.services.renewal_services import (
    get_pending,
    update_pending,
    mark_message_processed,
    get_all_pending_by_contact,
    is_message_processed_or_queued,
    try_lock_processing,
    add_pending_message,
    process_pending_messages,
    set_processing_status,
    get_or_create_session
)
from app.utils.utils import respond_with_200_on_exception, standardize_phone_number


webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)

# Estados válidos para negociações
VALID_STATUSES = [
    "pending",
    "info_sent",
    "customer_retention",
    "sale_created",
    "billing_generated",
    "billing_pdf_sent",
    "scheduling_form_sent",
    "complete",
]


@webhook_bp.route("/consulta-receita", methods=["POST"])
def valida_cnpj_receita_bitrix():
    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403

    required_params = ["idEmpresa", "CNPJ"]
    missing = [p for p in required_params if not request.args.get(p)]
    if missing:
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    id_empresa = request.args["idEmpresa"]
    cnpj = request.args["CNPJ"]
    raw = get_cnpj_receita(cnpj)
    if not raw:
        return jsonify({"error": "Dados do CNPJ não encontrados"}), 502

    processed = update_company_process_cnpj(raw, id_empresa)
    api_url = (
        "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.company.update"
    )
    response = post_destination_api(processed, api_url)
    return jsonify({"status": "received", "response": response}), 200


@webhook_bp.route("/aviso-certificado", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route(add_pending_if_missing=True)
def envia_comunicado_para_cliente_certif_digital_digisac():
    logger.info("/aviso-certificado recebido")

    # Validação de assinatura
    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        logger.warning("Assinatura inválida recebida em /aviso-certificado.")
        return jsonify({"error": "Assinatura inválida"}), 403

    # Extrair parâmetros
    args = request.args
    contact_number = args.get("contactNumber")
    company_name = args.get("companyName")
    contact_name = args.get("contactName")
    days_to_expire_str = args.get("daysToExpire")
    spa_id_str = args.get("idSPA")
    deal_type = args.get("dealType")

    # Validar parâmetros obrigatórios
    required = {
        "contactNumber": contact_number,
        "companyName": company_name,
        "contactName": contact_name,
        "daysToExpire": days_to_expire_str,
        "idSPA": spa_id_str,
        "dealType": deal_type,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error(f"Parâmetros obrigatórios ausentes: {', '.join(missing)}")
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios ausentes: {', '.join(missing)}"}
            ),
            400,
        )

    # Converter tipos
    try:
        days_to_expire = int(days_to_expire_str)
        spa_id = int(spa_id_str)
    except ValueError:
        logger.error("Valores inválidos para daysToExpire ou idSPA")
        return jsonify({"error": "daysToExpire e idSPA devem ser inteiros"}), 400

    # Gerar e verificar duplicidade
    webhook_id = f"cert_exp_{spa_id}_{datetime.utcnow().timestamp()}"
    if is_message_processed_or_queued(spa_id, webhook_id):
        logger.info(f"Duplicado: {webhook_id} para SPA {spa_id}")
        return jsonify({"status": "ignored", "message": "Evento já processado"}), 200

    std_number = standardize_phone_number(contact_number)

    # Notificações
    try:
        build_transfer_to_certification(std_number)
        build_certification_message(
            std_number, contact_name, company_name, days_to_expire, deal_type
        )
        add_comment_crm_timeline(
            {
                "ENTITY_ID": spa_id,
                "ENTITY_TYPE": "DYNAMIC_137",
                "COMMENT": f"Aviso enviado em {datetime.now():%Y-%m-%d %H:%M}",
            }
        )
    except Exception as e:
        logger.exception(f"Erro ao executar notificações SPA {spa_id}: {e}")

    # Atualizar estado e marca duplicação
    update_pending(spa_id=spa_id, status="pending", last_interaction=datetime.now())
    mark_message_processed(
        spa_id=spa_id,
        message_id=webhook_id,
        event_type="cert_expiration",
        payload=json.dumps(request.args.to_dict()),
    )

    return jsonify({"status": "success", "spa_id": spa_id}), 200


@webhook_bp.route("/digisac", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def resposta_certificado_digisac():
    logger.info("/digisac recebido")
    payload = request.get_json(silent=True) or {}
    data = payload.get("data", {}) or {}
    message = data.get("message", {}) or {}
    message_id = message.get("id")
    contact_id = data.get("contactId")

    # Traduz contato para número
    contact_number = _get_contact_number_by_id(contact_id)
    if not contact_number:
        return jsonify({"status": "ignored", "reason": "Contato não encontrado"}), 200

    # Seleciona a próxima SPA elegível
    pending = get_pending(contact_number=contact_number, context_aware=True)
    if not pending:
        all_pendings = get_all_pending_by_contact(contact_number)
        return (
            jsonify(
                {
                    "status": "ignored",
                    "reason": "Sem pendência ativa",
                    "pendings": all_pendings,
                }
            ),
            200,
        )

    spa_id = pending["spa_id"]

    # Deduplicação de evento
    if is_message_processed_or_queued(spa_id, message_id):
        logger.info(f"Mensagem {message_id} duplicada para SPA {spa_id}")
        return jsonify({"status": "duplicate"}), 200

    mark_message_processed(
        spa_id=spa_id,
        message_id=message_id,
        event_type="digisac_incoming",
        payload=json.dumps(payload),
    )
    # Cria/atualiza sessão ANTES de processar a mensagem
    get_or_create_session(contact_number)

    # Se já estiver processando, enfileira e notifica (se for primeira vez)
    if not try_lock_processing(spa_id):
        add_pending_message(spa_id, payload)
        """
        // Fluxo de mensagens de comando inválido não completo melhorar posteriormente
        try:
            processing_contact = pending.get("contact_number")

            if not has_recent_notification(spa_id, "processing_notification", minutes=5):
                send_processing_notification(processing_contact)
                mark_notification_event(spa_id, "processing_notification")

        except Exception:
            logger.exception("Falha ao enviar notificação de processamento")
        """

        return jsonify({"status": "queued"}), 200

    # Lock obtido → processa, libera e esvazia fila
    try:
        _process_digisac_message(spa_id, message.get("text", ""))
    finally:
        set_processing_status(spa_id, False)
        process_pending_messages(spa_id, _process_digisac_message)

    return jsonify({"status": "processed", "spa_id": spa_id}), 200


def _process_digisac_message(spa_id: int, user_message: str):
    """Processa a mensagem do usuário e atualiza o estado do negócio"""
    # Obter dados atualizados da pendência
    pending = get_pending(spa_id=spa_id, context_aware=True)
    if not pending:
        logger.warning(f"Pendência não encontrada para SPA {spa_id}")
        return

    current_status = pending["status"]

    # Interpretar a resposta do usuário
    action = interpret_certification_response(user_message)
    logger.info(f"Ação detectada: {action} (Estado atual: {current_status})")
    if action in ["renew", "info", "refuse"]:
        from app.services.renewal_services import record_command, try_finalize_session
        record_command(pending["contact_number"])
        try_finalize_session(pending["contact_number"])

    # Executar ações com base na intenção
    if action == "renew" and current_status in ["pending", "info_sent"]:
        _handle_renew_action(spa_id, pending)
    elif action == "info" and current_status == "pending":
        _handle_info_action(spa_id, pending)
    elif action == "refuse" and current_status != "customer_retention":
        _handle_refuse_action(spa_id)
    else:
        logger.info(f"Ação {action} não aplicável no estado {current_status}")
        # //Melhorar o handle de comandos inválidos
        # _send_invalid_response_notification(contact_number)


def _handle_renew_action(spa_id: int, pending: dict):
    """Trata solicitação de renovação - fluxo revisado."""
    logger.info(f"Iniciando renovação para SPA ID {spa_id}")
    contact_number = pending["contact_number"]
    company_name = pending["company_name"]

    # Marca como em processamento para evitar duplicatas
    set_processing_status(spa_id, True)

    try:
        # Atualiza status imediatamente no DB
        update_pending(
            spa_id=spa_id,
            status="sale_creating",
            last_interaction=datetime.now(),
        )

        build_send_billing_message(
            contact_number=contact_number, company_name=company_name
        )

        # Cria a venda (idempotente)
        result = handle_sale_creation_certif_digital(
            contact_number, pending["deal_type"]
        )
        sale_id = result["sale"]["id"]

        # Atualiza CRM com o novo stage e sale_id
        update_crm_item(137, spa_id, {"stageId": "DT137_36:UC_90X241"})
        update_pending(
            spa_id=spa_id,
            sale_id=sale_id,
            status="sale_created",
            last_interaction=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Erro criando venda para SPA {spa_id}: {e}")
        # opcional: rollback de status ou incrementar retry_count
        update_pending(
            spa_id=spa_id,
            status="pending",
            retry_count=pending.get("retry_count", 0) + 1,
            last_interaction=datetime.now(),
        )
        raise
    finally:
        set_processing_status(spa_id, False)
    # Só depois de tudo: envia a proposta via Digisac
    # send_proposal_file(contact_number, company_name, spa_id)
    # logger.info(f"Proposta enviada para SPA {spa_id}")


def _handle_info_action(spa_id: int, pending: dict):
    """Trata solicitação de informações"""
    logger.info(f"Enviando informações para SPA ID {spa_id}")
    contact_number = pending["contact_number"]

    # Atualizar estado
    update_pending(
        spa_id=spa_id,
        status="info_sent",
        last_interaction=datetime.now(),
    )
    logger.info(f"Informações enviadas para SPA ID {spa_id}")

    build_transfer_to_certification(contact_number=contact_number)

    # Enviar proposta
    # send_proposal_file(contact_number, company_name, spa_id)


def _handle_refuse_action(spa_id: int):
    """Trata recusa do cliente"""
    logger.info(f"Registrando recusa para SPA ID {spa_id}")

    # Atualizar estado
    update_pending(
        spa_id=spa_id,
        status="customer_retention",
        last_interaction=datetime.now(),
    )

    # Atualizar CRM
    update_crm_item(137, spa_id, {"stageId": "DT137_36:UC_AY5334"})
    logger.info(f"Recusa registrada para SPA ID {spa_id}")


def _send_invalid_response_notification(contact_number: str):
    """Notifica o cliente sobre resposta inválida"""
    logger.info(f"Enviando notificação de resposta inválida para {contact_number}")
    try:
        send_processing_notification(contact_number)
    except Exception as e:
        logger.error(f"Erro ao enviar notificação: {str(e)}")


@webhook_bp.route("/cobranca-gerada", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def cobranca_gerada():
    logger.info("/cobranca-gerada recebido — salvando dados de cobrança")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    deal_id = request.args.get("dealId")

    if not contact_number:
        return jsonify({"error": "contactNumber ausente"}), 400

    pending = get_pending(contact_number)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        info = extract_billing_info(contact_number)
        update_pending(
            spa_id=pending.get("spa_id"),
            status="billing_generated",
            financial_event_id=info["financial_event_id"],
            last_interaction=datetime.now(),
        )

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "UF_CRM_1751478607": info["boleto_url"],
            },
        )

        close_ticket_digisac(contact_number)

        return (
            jsonify(
                {
                    "status": "billing_generated",
                    "message": "Cobrança identificada e status atualizado",
                    "event_id": info["financial_event_id"],
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao processar cobrança: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/envio-cobranca", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def envio_cobranca():
    logger.info("/envio-cobranca recebido — enviando boleto via Digisac")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    params = request.args or request.get_json(silent=True) or {}
    spa_id = params.get("idSPA")
    deal_id = params.get("idDeal")

    if not deal_id or not spa_id:
        return jsonify({"error": f"idSPA {spa_id} ou idDeal {deal_id} ausentes"}), 400

    pending = get_pending(spa_id=spa_id)
    if not pending or not isinstance(pending, dict):
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        build_billing_certification_pdf(
            contact_number=pending.get("contact_number"),
            company_name=pending.get("company_name"),
            deal_id=deal_id,
            filename=f"Cobrança_certificado_digital_-_{pending.get('company_name', '')}.pdf",
        )

        update_pending(
            spa_id=pending.get("spa_id"),
            status="billing_pdf_sent",
            last_interaction=datetime.now(),
        )

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "STAGE_ID": "C18:PREPARATION",
            },
        )

        close_ticket_digisac(pending.get("contact_number"))

        return (
            jsonify(
                {
                    "status": "billing_sent",
                    "message": "Boleto enviado com sucesso via Digisac",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao enviar boleto: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/agendamento-certificado", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def envia_form_agendamento_digisac() -> dict:
    """Função para envio de formulário para agendamento ao cliente"""
    logger.info(
        "/agendamento-certificado recebido, enviando agendamento de videoconferência"
    )
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403
    try:
        company_name = request.args.get("companyName")
        contact_number = request.args.get("contactNumber")
        schedule_form_link = request.args.get("linkFormAgendamento")
        spa_id = request.args.get("idSPA")

        build_form_agendamento(contact_number, company_name, schedule_form_link)
        update_pending(
            spa_id=spa_id,
            status="scheduling_form_sent",
            last_interaction=datetime.now(),
        )
        close_ticket_digisac(contact_number)

        return (
            jsonify(
                {
                    "status": "success",
                    "message": """
                    Formulário para agendamento de 
                    videoconferência enviado com sucesso
                    """,
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Erro ao enviar agendamento: %s", str(e))
        return jsonify({"error": str(e)}), 500
