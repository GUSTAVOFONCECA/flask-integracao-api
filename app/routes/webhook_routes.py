# app/routes/webhook_routes.py
import json
import logging
from flask import Blueprint, request, jsonify
from app.services.webhook_services import (
    get_cnpj_receita,
    update_company_process_cnpj,
    post_destination_api,
)

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)


@webhook_bp.route("/consulta-receita", methods=["POST"])
def post_webhook_valida_cnpj_receita():
    """---ajustar validação de chaves
    signature = request.headers.get('X-Signature')
    if not verify_webhook_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 403
    """
    # Validar parâmetros obrigatórios
    missing = [param for param in ["idEmpresa", "CNPJ"] if not request.args.get(param)]
    if missing:
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    post_url = (
        "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.company.update"
    )

    # lê só query-params
    id_empresa = request.args.get("idEmpresa")
    cnpj = request.args.get("CNPJ")
    id_card_crm = request.args.get("idCardCRM")

    logger.info(
        f"\n✅ Income webhook!\nRequest:\n{request}\nidEmpresa:  {id_empresa}\nCNPJ:       {cnpj}\nidCardCRM:  {id_card_crm}\n"
    )

    # Consulta API CNPJ receita, processa e post dados para contrato na entidade "empresa"(company)
    raw_cnpj_json = get_cnpj_receita(cnpj)
    data = update_company_process_cnpj(
        raw_cnpj_json=raw_cnpj_json, id_empresa=id_empresa
    )
    post_response = post_destination_api(processed_data=data, api_url=post_url)

    return (
        jsonify(
            {
                "status": "received",
                "response": json.dumps(post_response, indent=2, ensure_ascii=False),
            }
        ),
        200,
    )
