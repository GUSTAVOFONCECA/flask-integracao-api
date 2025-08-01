# app/routes/certificate_routes.py

"""Rotas para processo de certificação digital."""

import logging
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.core.container import Container
from app.utils.utils import respond_with_200_on_exception, standardize_phone_number
from app.services.digisac.digisac_services import queue_if_open_ticket_route

certificate_bp = Blueprint("certificate", __name__)
logger = logging.getLogger(__name__)


@certificate_bp.route("/aviso-certificado", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route(add_pending_if_missing=True)
def envia_comunicado_para_cliente_certif_digital_digisac():
    """Envia comunicado de vencimento de certificado para cliente via Digisac."""
    logger.info("Webhook /aviso-certificado recebido")

    # Get services from container
    container = Container()
    webhook_validator = container.get_webhook_validator()
    certificate_service = container.get_certificate_service()

    # Validação de assinatura
    signature = request.form.get("auth[member_id]", "")
    if not webhook_validator.verify_signature(signature):
        logger.warning("Assinatura inválida recebida em /aviso-certificado")
        return jsonify({"error": "Assinatura inválida"}), 403

    # Extrair e validar parâmetros
    args = request.args
    required_fields = [
        "contactNumber",
        "companyName",
        "document",
        "contactName",
        "daysToExpire",
        "idSPA",
        "dealType",
    ]

    params = {}
    missing = []

    for field in required_fields:
        value = args.get(field)
        if not value:
            missing.append(field)
        else:
            params[field] = value

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
        params["daysToExpire"] = int(params["daysToExpire"])
        params["idSPA"] = int(params["idSPA"])
    except ValueError:
        logger.error("Valores inválidos para daysToExpire ou idSPA")
        return jsonify({"error": "daysToExpire e idSPA devem ser inteiros"}), 400

    try:
        # Processar alerta de certificado
        result = certificate_service.process_certificate_alert(params)

        if result.get("status") == "duplicate":
            return (
                jsonify({"status": "ignored", "message": "Evento já processado"}),
                200,
            )

        return jsonify({"status": "success", "spa_id": params["idSPA"]}), 200

    except Exception as e:
        logger.exception(f"Erro ao processar alerta de certificado: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@certificate_bp.route("/digisac", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def resposta_certificado_digisac():
    """Processa resposta do cliente sobre certificação via Digisac."""
    logger.info("Webhook /digisac recebido")

    # Get services from container
    container = Container()
    certificate_service = container.get_certificate_service()

    payload = request.get_json(silent=True) or {}

    try:
        # Processar resposta do cliente
        result = certificate_service.process_customer_response(payload)

        if result.get("status") == "ignored":
            return jsonify(result), 200

        if result.get("status") == "duplicate":
            return jsonify({"status": "duplicate"}), 200

        if result.get("status") == "queued":
            return jsonify({"status": "queued"}), 200

        return jsonify({"status": "processed", "spa_id": result.get("spa_id")}), 200

    except Exception as e:
        logger.exception(f"Erro ao processar resposta do cliente: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500
