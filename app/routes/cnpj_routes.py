# app/routes/cnpj_routes.py

"""Rotas para operações de CNPJ e atualização de empresas."""

import logging
from flask import Blueprint, request, jsonify
from app.core.container import Container

cnpj_bp = Blueprint("cnpj", __name__)
logger = logging.getLogger(__name__)


@cnpj_bp.route("/consulta-receita", methods=["POST"])
def valida_cnpj_receita_bitrix():
    """Valida CNPJ na Receita Federal e atualiza empresa no Bitrix24."""
    logger.info("Iniciando validação de CNPJ via webhook")

    # Get services from container
    container = Container()
    webhook_validator = container.get_webhook_validator()
    cnpj_service = container.get_cnpj_service()

    # Validar assinatura do webhook
    signature = request.form.get("auth[member_id]", "")
    if not webhook_validator.verify_signature(signature):
        logger.warning("Assinatura inválida recebida em /consulta-receita")
        return jsonify({"error": "Assinatura inválida"}), 403

    # Validar parâmetros obrigatórios
    required_params = ["idEmpresa", "CNPJ"]
    missing = [p for p in required_params if not request.args.get(p)]
    if missing:
        logger.error(f"Parâmetros obrigatórios faltando: {', '.join(missing)}")
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    id_empresa = request.args["idEmpresa"]
    cnpj = request.args["CNPJ"]

    try:
        # Processar atualização de CNPJ
        result = cnpj_service.update_company_cnpj(cnpj, id_empresa)

        if not result:
            return jsonify({"error": "Dados do CNPJ não encontrados"}), 502

        logger.info(f"CNPJ {cnpj} atualizado com sucesso para empresa {id_empresa}")
        return jsonify({"status": "success", "response": result}), 200

    except Exception as e:
        logger.exception(f"Erro ao processar CNPJ {cnpj}: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500
