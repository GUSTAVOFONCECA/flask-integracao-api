# app/routes/webhook_routes.py

"""
Rotas de webhook para integração com Bitrix24 e validação de CNPJ.
"""

import logging
from werkzeug.exceptions import BadRequest
from flask import Blueprint, request, jsonify
from app.services.webhook_services import (
    get_cnpj_receita,
    update_company_process_cnpj,
    post_destination_api,
    verify_webhook_signature,
    send_message_digisac,
    transfer_ticket_digisac,
)

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)


@webhook_bp.route("/consulta-receita", methods=["POST"])
def post_valida_cnpj_receita_bitrix():
    """Endpoint para validação de CNPJ via webhook.

    :formparam idEmpresa: ID da empresa no sistema Bitrix24 (obrigatório)
    :formparam CNPJ: CNPJ a ser validado (obrigatório)
    :formparam idCardCRM: ID do card CRM (opcional)

    :return: JSON com status da operação e resposta da API
    :rtype: tuple[flask.Response, int]

    :raises HTTPException 400: Parâmetros obrigatórios faltando
    :raises HTTPException 403: Assinatura inválida
    :raises HTTPException 502: Erro na consulta à Receita Federal

    .. rubric:: Exemplo de Requisição

    .. code-block:: http

        POST /webhooks/consulta-receita?idEmpresa=123&CNPJ=00.000.000/0001-91
        X-Signature: sha256=abc123...

    .. rubric:: Exemplo de Resposta

    .. code-block:: json

        {
            "status": "received",
            "response": {
                "status_code": 200,
                "content": {"id": 456}
            }
        }
    """
    # Obter a assinatura DO FORMULÁRIO (não do header)
    signature = request.form.get("auth[member_id]", "")

    # Validar usando os dados BRUTOS da requisição (já URL-decoded)
    if not verify_webhook_signature(signature):
        logger.warning("⚠️ Assinatura inválida | Recebida: %s", signature)
        return jsonify({"error": "Assinatura inválida"}), 403
    # Validar parâmetros obrigatórios
    required_params = ["idEmpresa", "CNPJ"]
    missing = [param for param in required_params if not request.args.get(param)]

    if missing:
        logger.error("❌ Parâmetros obrigatórios faltando: %s", missing)
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    try:
        # Extrair parâmetros
        post_url = (
            "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.company.update"
        )
        id_empresa = request.args["idEmpresa"]
        cnpj = request.args["CNPJ"]

        logger.info(
            "ℹ️ Nova requisição de validação - ID Empresa: %s, CNPJ: %s",
            id_empresa,
            cnpj,
        )

        # Consultar dados do CNPJ
        raw_cnpj_json = get_cnpj_receita(cnpj)
        if not raw_cnpj_json:
            logger.error("❌ Falha na consulta do CNPJ %s", cnpj)
            return jsonify({"error": "Dados do CNPJ não encontrados"}), 502

        # Processar e enviar dados
        processed_data = update_company_process_cnpj(raw_cnpj_json, id_empresa)
        api_response = post_destination_api(processed_data, post_url)

        logger.info(
            "✅ CNPJ %s validado com sucesso para a empresa %s", cnpj, id_empresa
        )

        return (
            jsonify({"status": "received", "response": api_response}),
            200,
        )

    except (KeyError, ValueError, TypeError) as e:
        logger.critical("❌ Erro crítico no processamento: %s", str(e))
        return jsonify({"error": "Erro interno no processamento"}), 500


@webhook_bp.route("/aviso-certificado", methods=["POST"])
def post_envia_comunicado_para_cliente_bitrix():
    """Envia comunicação de expiração de certificado"""
    # Log detalhado da requisição
    logger.debug(f"→ Headers: {dict(request.headers)}")
    logger.debug(f"→ Raw Data: {request.get_data()!r}")

    try:
        data = request.get_json()
        logger.debug(f"→ JSON: {data}")
    except BadRequest:
        return jsonify({"error": "Invalid JSON"}), 400

    # Extrair parâmetros necessários
    required = [
        "contact_id",
        "user_id",
        "department_id",
        "contact_name",
        "company_name",
    ]
    if not all(key in data for key in required):
        return jsonify({"error": "Missing required parameters"}), 400

    # Enviar mensagem
    result = send_message_digisac(
        contact_id=data["contact_id"],
        user_id=data["user_id"],
        department_id=data["department_id"],
        contact_name=data["contact_name"],
        company_name=data["company_name"],
    )

    if "error" in result:
        return jsonify(result), 500

    return (
        jsonify(
            {
                "status": "success",
                "message": "Comunicação enviada",
                "digisac_response": result,
            }
        ),
        200,
    )


@webhook_bp.route("/renova-certificado", methods=["POST"])
def post_renova_certificado_digisac():
    """Processa resposta de renovação de certificado"""
    # Log detalhado da requisição
    logger.debug(f"→ Headers: {dict(request.headers)}")
    logger.debug(f"→ Raw Data: {request.get_data()!r}")

    try:
        data = request.get_json()
        logger.debug(f"→ JSON: {data}")
    except BadRequest:
        return jsonify({"error": "Invalid JSON"}), 400

    # Verificar se é mensagem válida
    if data.get("origin") != "contact" or "text" not in data:
        return jsonify({"status": "ignored"}), 200

    # Processar resposta
    resposta = data["text"].strip()
    contact_id = data.get("contactId")
    ticket = data.get("ticket", {})

    if resposta == "1":  # Cliente quer renovar
        result = transfer_ticket_digisac(
            contact_id=contact_id,
            department_id=Config.RENOVACAO_DEPARTMENT_ID,
            user_id=None,
            comments="Cliente solicitou renovação de certificado",
        )

        if "error" in result:
            return jsonify(result), 500

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Ticket transferido para renovação",
                    "digisac_response": result,
                }
            ),
            200,
        )

    elif resposta == "2":  # Cliente não quer renovar
        return (
            jsonify({"status": "success", "message": "Cliente recusou renovação"}),
            200,
        )

    return jsonify({"status": "ignored"}), 200


@webhook_bp.route("/nao-renova-certificado", methods=["POST"])
def post_nao_renova_certificado_digisac():
    # ─── DEBUG: tudo que chega na requisição ──────────────────────────────
    # Query string (args)
    logger.debug("→ Query String args: %s", request.args.to_dict(flat=False))
    # Cabeçalhos
    logger.debug("→ Headers: %s", dict(request.headers))
    # Payload raw
    logger.debug("→ Raw Data: %r", request.get_data())
    # JSON (se houver)
    try:
        json_payload = request.get_json(silent=True)
    except BadRequest as e:
        json_payload = f"<invalid JSON: {e}>"
    logger.debug("→ JSON: %s", json_payload)
    # Form fields (application/x-www-form-urlencoded ou multipart/form-data)
    logger.debug("→ Form: %s", request.form.to_dict(flat=False))
    # Arquivos (se houver upload)
    logger.debug("→ Files: %s", list(request.files.keys()))
    # Valores combinados (args + form)
    logger.debug("→ Values (args+form): %s", request.values.to_dict(flat=False))
