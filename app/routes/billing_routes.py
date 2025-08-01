# app/routes/billing_routes.py

"""Rotas para operações de cobrança e faturamento."""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.core.container import Container
from app.utils.utils import respond_with_200_on_exception
from app.services.digisac.digisac_services import queue_if_open_ticket_route

billing_bp = Blueprint("billing", __name__)
logger = logging.getLogger(__name__)


@billing_bp.route("/cobranca-gerada", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def cobranca_gerada():
    """Processa evento de cobrança gerada."""
    logger.info("Webhook /cobranca-gerada recebido")

    # Get services from container
    container = Container()
    billing_service = container.get_billing_service()

    # Extrair parâmetros
    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    deal_id = request.args.get("dealId")

    if not contact_number:
        logger.error("contactNumber ausente na requisição")
        return jsonify({"error": "contactNumber ausente"}), 400

    try:
        # Processar cobrança gerada
        result = billing_service.process_billing_generated(contact_number, deal_id)

        if result.get("status") == "not_found":
            return jsonify({"error": "Nenhuma solicitação pendente"}), 404

        return (
            jsonify(
                {
                    "status": "billing_generated",
                    "message": "Cobrança identificada e status atualizado",
                    "event_id": result.get("event_id"),
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Erro ao processar cobrança: {e}")
        return jsonify({"error": str(e)}), 500


@billing_bp.route("/envio-cobranca", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def envio_cobranca():
    """Processa envio de cobrança via Digisac."""
    logger.info("Webhook /envio-cobranca recebido")

    # Get services from container
    container = Container()
    billing_service = container.get_billing_service()

    # Extrair parâmetros
    params = request.args or request.get_json(silent=True) or {}
    spa_id = params.get("idSPA")
    deal_id = params.get("idDeal")

    if not deal_id or not spa_id:
        logger.error(f"Parâmetros ausentes - idSPA: {spa_id}, idDeal: {deal_id}")
        return jsonify({"error": f"idSPA {spa_id} ou idDeal {deal_id} ausentes"}), 400

    try:
        # Processar envio de cobrança
        result = billing_service.process_billing_send(spa_id, deal_id)

        if result.get("status") == "not_found":
            return jsonify({"error": "Nenhuma solicitação pendente"}), 404

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
        logger.exception(f"Erro ao enviar boleto: {e}")
        return jsonify({"error": str(e)}), 500
