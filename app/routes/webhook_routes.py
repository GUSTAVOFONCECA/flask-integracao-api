# app/routes/webhook_routes.py

"""
Rotas de webhook para integração com Bitrix24 e validação de CNPJ.
"""

import time
import logging
from werkzeug.exceptions import BadRequest
from flask import Blueprint, request, jsonify
from app.services.webhook_services import (
    get_cnpj_receita,
    update_company_process_cnpj,
    post_destination_api,
    verify_webhook_signature,
    get_contact_id_by_number,
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
            "ℹ️ Nova requisição de validação de CNPJ - ID Empresa: %s, CNPJ: %s",
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
    # Obter a assinatura DO FORMULÁRIO (não do header)
    signature = request.form.get("auth[member_id]", "")

    # Validar usando os dados BRUTOS da requisição (já URL-decoded)
    if not verify_webhook_signature(signature):
        logger.warning("⚠️ Assinatura inválida | Recebida: %s", signature)
        return jsonify({"error": "Assinatura inválida"}), 403
    # Validar parâmetros obrigatórios
    required_params = ["companyName", "contactName", "contactNumber", "daysToExpire"]
    missing = [param for param in required_params if not request.args.get(param)]

    if missing:
        logger.error("❌ Parâmetros obrigatórios faltando: %s", missing)
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    # Get params da query da request
    company_name = request.args["companyName"]
    contact_name = request.args["contactName"]
    contact_number = request.args["contactNumber"]
    days_to_expire = request.args["daysToExpire"]

    logger.info(
        "ℹ️ Nova requisição de aviso do vencimento de CD\n"
        "Empresa: %s\nContato: %s\nNúmero: %s\nDias para expirar: %s",
        company_name,
        contact_name,
        contact_number,
        days_to_expire,
    )

    # Buscar contact ID - FUNÇÃO ATUALIZADA
    contact_id = get_contact_id_by_number(contact_number)

    if not contact_id:
        logger.error("❌ Contact ID não encontrado para o número: %s", contact_number)
        return jsonify({"error": "Número não encontrado no sistema"}), 404

    # Abrir chamado
    transfer_ticket_digisac(
        contact_id=contact_id,
    )
    time.sleep(1)

    # Enviar mensagem
    result = send_message_digisac(
        contact_id=contact_id,
        contact_name=contact_name,
        company_name=company_name,
        days_to_expire=days_to_expire,
    )

    if "error" in result:
        logger.error("❌ Falha ao enviar mensagem: %s", result["error"])
        return jsonify(result), 500

    return (
        jsonify(
            {
                "status": "success",
                "message": "Mensagem enviada com sucesso",
                "digisac_response": result,
            }
        ),
        200,
    )


@webhook_bp.route("/renova-certificado", methods=["POST"])
def post_renova_certificado_digisac():
    """Processa resposta de renovação de certificado"""
    # Log detalhado da requisição
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


@webhook_bp.route("/nao-renova-certificado", methods=["POST"])
def post_nao_renova_certificado_digisac():
    """Processa resposta de não renovação de certificado"""
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
