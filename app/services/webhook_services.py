"""
Service for managing webhooks and subprocess of getting CNPJ data processing
and posting to Bitrix24.
"""
# app/routes/webhook_services.py

import hmac
import re
import json
import logging
from functools import wraps
import requests
from flask import request, jsonify
from app.config import Config


logger = logging.getLogger(__name__)


def validate_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if api_key != Config.API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def verify_webhook_signature(data, signature):
    """
    Verify webhook signature using HMAC-SHA256.

    Args:
        data: The raw request data
        signature: The signature from request headers

    Returns:
        bool: True if signatures match, False otherwise
    """
    if not Config.WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET not configured")
        return False

    if not data or not signature:
        logger.error("Missing data or signature")
        return False

    try:
        expected = hmac.new(
            Config.WEBHOOK_SECRET.encode("utf-8"), data, "sha256"
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    except (TypeError, ValueError) as e:
        logger.error("Error verifying signature: %s", str(e))
        return False


def get_cnpj_receita(cnpj: str) -> None:
    cnpj_int = re.sub(pattern=r"[\.\/-]", repl="", string=str(cnpj))

    url = f"https://publica.cnpj.ws/cnpj/{cnpj_int}"

    try:
        response = requests.get(url=url, timeout=60)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            logger.critical("\n❌ Erro na requisição API:\n%s\n",
                            json.dumps({data['error']}, indent=2, ensure_ascii=False))
        else:
            logger.info(
                "\n✅ Sucesso na consulta do CNPJ %s\nPayload:\n%s\n",
                cnpj,
                json.dumps(data, indent=2, ensure_ascii=False)
            )
            
            return data

    except requests.exceptions.RequestException as e:
        logger.critical("\n❌ Exceção na requisição API:\n%s\n", str(e))


def update_company_process_cnpj(raw_cnpj_json: dict, id_empresa: str) -> dict:

    # Extrair dados do estabelecimento
    company = raw_cnpj_json.get("estabelecimento", {})

    # Complemento tratado
    complemento_raw = company.get("complemento", "")
    complemento = re.sub(r"\s{2,}", " ", complemento_raw).strip()

    # Componentes de endereço
    tipo_logradouro = company.get("tipo_logradouro", "")
    logradouro = company.get("logradouro", "")
    numero = company.get("numero", "")
    bairro = company.get("bairro", "")
    cidade = company.get("cidade", {}).get("nome", "")
    estado = company.get("estado", {}).get("nome", "")

    # Endereço completo
    endereco = f"{tipo_logradouro} {logradouro}, N° {numero}, {complemento}".strip()

    # Inscrição estadual
    inscricoes = company.get("inscricoes_estaduais", [])
    inscricao_estadual = inscricoes[0] if inscricoes else "Não Contribuinte"

    # CNPJ formatado
    cnpj_formatado = re.sub(
        r"(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})",
        r"\1.\2.\3/\4-\5",
        company.get("cnpj", ""),
    )

    # CEP formatado
    cep_formatado = re.sub(
        r"(\d{2})(\d{3})(\d{3})", r"\1.\2-\3", company.get("cep", "")
    )

    # Mapeamento dos campos do CRM
    fields_mapping = [
        "id",  # str(id_empresa)
        "UF_CRM_1708977581412",  # cnpj
        "TITLE",  # nome
        "UF_CRM_1709838249844",  # nome_fantasia
        "ADDRESS",  # endereco
        "ADDRESS_REGION",  # bairro (não uso region, pois pode ser utilizado para estratégias de comercialização)
        "ADDRESS_CITY",  # cidade
        "ADDRESS_PROVINCE",  # estado
        "ADDRESS_POSTAL_CODE",  # cep
        "UF_CRM_1710938520402",  # inscricao_estadual
        "UF_CRM_1720974662288",  # empresa sincronizada com a receita
    ]

    # Dados processados
    processed_data = {
        fields_mapping[0]: str(id_empresa),
        "fields": {
            fields_mapping[1]: cnpj_formatado,
            fields_mapping[2]: raw_cnpj_json.get("razao_social", ""),
            fields_mapping[3]: company.get("nome_fantasia", ""),
            fields_mapping[4]: endereco,
            fields_mapping[5]: bairro,
            fields_mapping[6]: cidade,
            fields_mapping[7]: estado,
            fields_mapping[8]: cep_formatado,
            fields_mapping[9]: inscricao_estadual,
            fields_mapping[10]: "Y",
        },
        "params": {"REGISTER_SONET_EVENT": "N"},
    }

    logger.info(
        "\n✅ Processed data:\n%s\n",
        json.dumps(processed_data, indent=2, ensure_ascii=False)
    )
    return processed_data


def post_destination_api(processed_data: dict, api_url: str) -> dict:
    response = None
    try:
        response = requests.post(api_url, json=processed_data, timeout=10)
        response.raise_for_status()

        # Extrair dados relevantes da resposta
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.json(),  # Ou response.text se não for JSON
        }

        logger.info(
            "\n✅ Validação CNPJ concluída\n• Empresa: %s\n• Resposta: %s\n",
            json.dumps([
                processed_data['fields']["UF_CRM_1708977581412"],  # cnpj
                processed_data['fields']["TITLE"]  # nome
            ]),
            json.dumps(response_data, indent=2, ensure_ascii=False)
        )

        return response_data

    except requests.exceptions.JSONDecodeError:
        logger.warning("\n⚠️ Resposta não é JSON válido, retornando texto\n")
        return {"content": response.text} if response else {"error": "No response"}
    except requests.exceptions.Timeout:
        logger.error("\n❌ Timeout na requisição\n")
        return {"error": "Timeout"}

    except requests.exceptions.RequestException as e:
        logger.error("\n❌ Erro na requisição:\n%s\n", str(e))
        return {"error": str(e)}
