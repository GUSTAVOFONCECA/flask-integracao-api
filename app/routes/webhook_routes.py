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
    update_crm_item_certif_digital,
)

# Importar wrappers do fluxo de Certificação Digital
from app.services.webhook_services import (
    build_certification_transfer,
    build_certification_message,
    build_billing_certification_pdf,
    build_form_agendamento,
)
from app.services.conta_azul.conta_azul_services import (
    handle_sale_creation_certif_digital,
    handle_billing_generated_certif_digital,
)
from app.services.renewal_services import (
    add_pending,
    get_pending,
    update_pending,
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
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403

    params = request.args
    required = [
        "cardID",
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

    card_id = int(params["cardID"])
    contact_name = params["contactName"]
    company_name = params["companyName"]
    contact_number = params["contactNumber"]
    days_to_expire = int(params["daysToExpire"])
    deal_type = params["dealType"]

    # Fluxo Certificação Digital
    build_certification_transfer(contact_number)
    time.sleep(1)
    result = build_certification_message(
        contact_number, contact_name, company_name, days_to_expire
    )

    std_number = add_pending(company_name, contact_number, deal_type, card_id)
    update_crm_item_certif_digital(
        card_id=card_id,
        fields={
            "ufCrm18_1740158577862": datetime.now().strftime("%Y-%m-%d"),
            "ufCrm18_1746464219165": "Enviado notificação para renovação via digisac",
        },
    )

    if "error" in result:
        return jsonify(result), 500

    return (
        jsonify(
            {
                "status": "success",
                "std_phone": std_number,
                "card_id": card_id,
                "message": "Comunicação enviada",
                "digisac_response": result,
            }
        ),
        200,
    )


@webhook_bp.route("/renova-certificado", methods=["POST"])
def renova_certificado_digisac():
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    if not contact_number:
        return jsonify({"error": "contactNumber ausente"}), 400

    pending = get_pending(contact_number)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        # Apenas cria a venda e retorna sale_id
        result = handle_sale_creation_certif_digital(
            contact_number, pending["deal_type"]
        )
        sale = result["sale"]
        sale_id = sale.get("id") or sale.get("venda", {}).get("id")
        update_pending(pending["card_crm_id"], status="sale_created", sale_id=sale_id)

        return (
            jsonify(
                {
                    "status": "sale_created",
                    "sale_id": sale_id,
                    "message": "Venda criada com sucesso. Aguardando geração de boleto.",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao criar venda: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/cobranca-gerada", methods=["POST"])
def envia_cobranca_digisac():
    logger.debug(f"Headers: %s", dict(request.headers))
    logger.debug(f"Args:    %s", request.args.to_dict())
    logger.debug(f"Form:    %s", request.form.to_dict())
    logger.debug(f"JSON:    %s", request.get_json(silent=True))

    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403

    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    if not contact_number:
        return jsonify({"error": "contactNumber ausente"}), 400

    pending = get_pending(contact_number)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        # Chama o serviço para processar o envio da cobrança
        result = handle_billing_generated_certif_digital(contact_number)

        # Se tudo ocorrer bem, retorna sucesso
        return (
            jsonify(
                {
                    "status": "billing_pdf_sent",
                    "message": "Boleto baixado e enviado com sucesso",
                    "pdf_url": result.get(
                        "pdf_url", ""
                    ),  # Adiciona URL para referência
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao enviar boleto: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/nao-renova-certificado", methods=["POST"])
def nao_renova_certificado_digisac():
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    if not contact_number:
        return jsonify({"error": "contactNumber ausente"}), 400

    pending = get_pending(contact_number)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        update_crm_item_certif_digital(
            card_id=pending["card_crm_id"], fields={"stageId": "DT137_36:UC_AY5334"}
        )
        update_pending(pending["card_crm_id"], "customer_retention")
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Card enviado para retenção com sucesso",
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Erro ao recusar certificado: %s", str(e))
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/agendamento-certificado", methods=["POST"])
def envia_form_agendamento_digisac() -> dict:
    """Função para envio de formulário para agendamento ao cliente"""
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
        card_id = request.args.get("idSPA")

        build_form_agendamento(contact_number, company_name, schedule_form_link)
        update_pending(card_id, "scheduling_form_sent")

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Formulário para agendamento \
                        de videoconferência enviado com sucesso",
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Erro ao enviar agendamento: %s", str(e))
        return jsonify({"error": str(e)}), 500
