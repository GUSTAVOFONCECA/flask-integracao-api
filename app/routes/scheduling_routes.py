
# app/routes/scheduling_routes.py

"""Rotas para operações de agendamento."""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.core.container import Container
from app.utils.utils import respond_with_200_on_exception
from app.services.digisac.digisac_services import queue_if_open_ticket_route

scheduling_bp = Blueprint("scheduling", __name__)
logger = logging.getLogger(__name__)


@scheduling_bp.route("/agendamento-certificado", methods=["POST"])
@respond_with_200_on_exception
@queue_if_open_ticket_route()
def envia_form_agendamento_digisac():
    """Envia formulário de agendamento para videoconferência."""
    logger.info("Webhook /agendamento-certificado recebido")
    
    # Get services from container
    container = Container()
    webhook_validator = container.get_webhook_validator()
    scheduling_service = container.get_scheduling_service()
    
    # Validar assinatura
    signature = request.form.get("auth[member_id]", "")
    if not webhook_validator.verify_signature(signature):
        logger.warning("Assinatura inválida recebida em /agendamento-certificado")
        return jsonify({"error": "Assinatura inválida"}), 403

    # Extrair parâmetros
    args = request.args
    required_fields = ["companyName", "contactNumber", "linkFormAgendamento", "idSPA"]
    
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
        return jsonify({
            "error": f"Parâmetros obrigatórios ausentes: {', '.join(missing)}"
        }), 400

    try:
        # Processar envio de formulário de agendamento
        result = scheduling_service.send_scheduling_form(params)
        
        return jsonify({
            "status": "success",
            "message": "Formulário para agendamento de videoconferência enviado com sucesso"
        }), 200
        
    except Exception as e:
        logger.exception(f"Erro ao enviar agendamento: {e}")
        return jsonify({"error": str(e)}), 500
