# app/routes/webhook_routes.py

"""
Rotas de webhook para integração com Bitrix24 e validação de CNPJ.
"""

import time
from datetime import datetime
import logging
import requests
from flask import Blueprint, request, jsonify

from app.services.webhook_services import (
    get_cnpj_receita,
    update_company_process_cnpj,
    post_destination_api,
    verify_webhook_signature,
    update_crm_item,
    update_deal_item,
    _get_contact_id_by_number,
    add_comment_crm_timeline,
)

# Importar wrappers do fluxo de Certificação Digital
from app.services.webhook_services import (
    interpret_certification_response,
    send_proposal_file,
    build_transfer_to_certification,
    build_certification_message,
    build_form_agendamento,
    build_billing_certification_pdf,
)

from app.services.conta_azul.conta_azul_services import (
    handle_sale_creation_certif_digital,
    extract_billing_info,
)

from app.services.renewal_services import (
    add_pending,
    get_pending,
    update_pending,
    check_pending_status,
    is_message_processed,
    mark_message_processed,
    complete_pending,
)

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)


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
def envia_comunicado_para_cliente_certif_digital_digisac():
    logger.info("/aviso-certificado recebido, criando pendência")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403

    params = request.args
    required = [
        "spaId",
        "companyName",
        "contactName",
        "contactNumber",
        "daysToExpire",
        "dealType",
    ]
    missing = [p for p in required if not params.get(p)]
    if missing:
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    spa_id = int(params["spaId"])
    contact_name = params["contactName"]
    company_name = params["companyName"]
    contact_number = params["contactNumber"]
    days_to_expire = int(params["daysToExpire"])
    deal_type = params["dealType"]

    # Verificar se já existe pendência para este spa_id
    existing = get_pending(spa_id=spa_id)
    if existing and existing.get("digisac_ticket_id"):
        logger.info(f"Ticket já existe para SPA {spa_id}")
        return (
            jsonify(
                {
                    "status": "exists",
                    "message": "Ticket já existe para este negócio",
                    "ticket_id": existing["digisac_ticket_id"],
                }
            ),
            200,
        )

    # Fluxo Certificação Digital
    transfer_result = build_transfer_to_certification(contact_number)

    # Se já existe ticket ativo, usa o existente
    if transfer_result.get("status") == "ticket_exists":
        existing = get_pending(contact_number=contact_number)
        if existing:
            ticket_id = existing["digisac_ticket_id"]
            contact_id = existing["digisac_contact_id"]
        else:
            return (
                jsonify({"error": "Ticket existe mas não encontrado no sistema"}),
                500,
            )
    else:
        time.sleep(1)
        result = build_certification_message(
            contact_number, contact_name, company_name, days_to_expire
        )
        ticket_id = result["ticketId"]
        contact_id = _get_contact_id_by_number(contact_number)

    # Adicionar pendência com contactId
    std_number = add_pending(
        company_name=company_name,
        contact_number=contact_number,
        deal_type=deal_type,
        spa_id=spa_id,
        digisac_contact_id=contact_id,
        digisac_ticket_id=ticket_id,
    )

    add_comment_crm_timeline(
        fields={
            "ENTITY_ID": spa_id,
            "ENTITY_TYPE": "DYNAMIC_137",
            "COMMENT": (
                "Enviado notificação para renovação via digisac "
                f"em {datetime.now().strftime("%Y-%m-%d %H:%M")}"
            ),
        },
    )

    if "error" in result:
        return jsonify(result), 500

    return (
        jsonify(
            {
                "status": "success",
                "std_phone": std_number,
                "spa_id": spa_id,
                "message": "Comunicação enviada",
                "digisac_response": result,
            }
        ),
        200,
    )


@webhook_bp.route("/digisac", methods=["POST"])
def resposta_certificado_digisac():
    logger.info("/digisac recebido")
    request_json = request.get_json(silent=True)

    # 1. Captura do ID único da mensagem
    msg = request_json.get("data", {}).get("message", {})
    message_id = msg.get("id") or msg.get("messageId")
    if message_id:
        # 2. Verifica duplicidade
        if is_message_processed(message_id):
            logger.info(f"Mensagem {message_id} já processada, ignorando.")
            return (
                jsonify({"status": "duplicate", "message": "Webhook já processado"}),
                200,
            )
        # 3. Marca para não processar de novo
        mark_message_processed(message_id)

    # 4. Continua com o fluxo original
    contact_id = request_json["data"]["contactId"]
    user_message = msg.get("text", "")

    pending = get_pending(contact_id=contact_id)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    response_type = interpret_certification_response(user_message)

    if response_type == "renew":
        if check_pending_status(pending["spa_id"], "sale_created"):
            logger.info(f"Renovação já processada para SPA {pending['spa_id']}")
            return (
                jsonify(
                    {
                        "status": "already_processed",
                        "message": "Renovação já foi processada",
                    }
                ),
                200,
            )
        try:
            send_proposal_file(
                pending["contact_number"], pending["company_name"], pending["spa_id"]
            )
            logger.info("Renovação solicitada, criando venda")
            result = handle_sale_creation_certif_digital(
                pending["contact_number"], pending["deal_type"]
            )
            sale = result["sale"]
            sale_id = sale.get("id") or sale.get("venda", {}).get("id")

            update_pending(pending["spa_id"], status="sale_created", sale_id=sale_id)

            update_crm_item(
                entity_type_id=137,
                spa_id=pending["spa_id"],
                fields={"stageId": "DT137_36:UC_90X241"},
            )

            return (
                jsonify(
                    {
                        "status": "sale_created",
                        "sale_id": sale_id,
                        "message": "Venda criada e proposta enviada com sucesso.",
                    }
                ),
                200,
            )

        except Exception as e:
            logger.exception("Erro ao criar venda: %s", e)
            return jsonify({"error": str(e)}), 500

    elif response_type == "info":
        if check_pending_status(pending["spa_id"], "info_sent"):
            logger.info(f"Informações já enviadas para SPA {pending['spa_id']}")
            return (
                jsonify(
                    {
                        "status": "already_sent",
                        "message": "Informações já foram enviadas",
                    }
                ),
                200,
            )
        try:
            logger.info("Cliente solicitou mais informações, enviando proposta")
            send_proposal_file(
                pending["contact_number"], pending["company_name"], pending["spa_id"]
            )
            update_pending(pending["spa_id"], "info_sent")

            return (
                jsonify(
                    {"status": "info_sent", "message": "Proposta enviada com sucesso."}
                ),
                200,
            )

        except Exception as e:
            logger.exception("Erro ao enviar proposta: %s", e)
            return jsonify({"error": str(e)}), 500

    elif response_type == "refuse":
        try:
            logger.info("Renovação recusada, enviando para retenção")
            update_crm_item(
                entity_type_id=137,
                spa_id=pending["spa_id"],
                fields={"stageId": "DT137_36:UC_AY5334"},
            )
            update_pending(pending["spa_id"], "customer_retention")
            return (
                jsonify(
                    {
                        "status": "refused",
                        "message": "Card enviado para retenção com sucesso",
                    }
                ),
                200,
            )

        except Exception as e:
            logger.exception("Erro ao recusar certificado: %s", str(e))
            return jsonify({"error": str(e)}), 500


@webhook_bp.route("/cobranca-gerada", methods=["POST"])
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
            spa_id=pending["spa_id"],
            status="billing_generated",
            financial_event_id=info["financial_event_id"],
        )

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "UF_CRM_1751478607": info["boleto_url"],
            },
        )

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
def envio_cobranca():
    logger.info("/envio-cobranca recebido — enviando boleto via Digisac")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    params = request.args or request.get_json(silent=True) or {}
    spa_id = params.get("spaId")
    deal_id = params.get("dealId")

    if not deal_id:
        return jsonify({"error": "spaId ausente"}), 400

    pending = get_pending(spa_id=spa_id)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        build_billing_certification_pdf(
            contact_number=pending["contact_number"],
            company_name=pending["company_name"],
            deal_id=deal_id,
            filename=f"Cobrança_certificado_digital_-_{pending['company_name']}.pdf",
        )

        update_pending(spa_id=pending["spa_id"], status="billing_pdf_sent")

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "STAGE_ID": "C18:PREPARATION",
            },
        )

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
        update_pending(spa_id, "scheduling_form_sent")

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
