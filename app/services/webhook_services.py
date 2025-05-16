# app/routes/webhook_services.py
import hmac
import re
import requests
import json
import logging
from functools import wraps
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
    expected = hmac.new(Config.WEBHOOK_SECRET.encode(), data, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature)


def get_cnpj_receita(cnpj: str) -> None:
    cnpj_int = re.sub(pattern=r"[\.\/-]", repl="", string=str(cnpj))

    url = f"https://publica.cnpj.ws/cnpj/{cnpj_int}"

    try:
        response = requests.get(url=url, timeout=60)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            logger.critical(f"\n❌ Erro na requisição API:\n{data['error']}\n")
        else:
            logger.info(
                f"\n✅ Sucesso na consulta do CNPJ {cnpj}\nPayload:\n{json.dumps(data, indent=2, ensure_ascii=False)}\n"
            )
            """
            with open(f"{cnpj_int}.json", "w", encoding="utf-8") as file:
                file.write(json.dumps(data, indent=2, ensure_ascii=False))
                file.close()
            """
            return data

    except requests.exceptions.RequestException as e:
        logger.critical(f"\n❌ Exceção na requisição API:\n{e}\n")


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
        f"\n✅ Processed data:\n{json.dumps(processed_data, indent=2, ensure_ascii=False)}\n"
    )
    return processed_data


def post_destination_api(processed_data: dict, api_url: str) -> dict:
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
            "\n✅ Validação CNPJ concluída"
            f"\n• Empresa: {json.dumps([
                                        processed_data['fields']["UF_CRM_1708977581412"], # cnpj
                                        processed_data['fields']["TITLE"]  # nome
                                    ])
                        }"
            f"\n• Resposta: {json.dumps(response_data, indent=2, ensure_ascii=False)}\n"
        )

        return response_data

    except requests.exceptions.JSONDecodeError:
        logger.warning("\n⚠️ Resposta não é JSON válido, retornando texto\n")
        return {"content": response.text}

    except requests.exceptions.RequestException as e:
        logger.error(f"\n❌ Erro na requisição:\n{str(e)}\n")
        return {"error": str(e)}
