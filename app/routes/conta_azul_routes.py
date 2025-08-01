# app/routes/conta_azul_routes.py
from flask import Blueprint, request, current_app, jsonify
from app.services.conta_azul.conta_azul_services import (
    auto_authenticate,
)

conta_azul_bp = Blueprint("conta_azul", __name__, url_prefix="/conta-azul")


@conta_azul_bp.route("/auto-auth")
def auto_auth():
    """Endpoint para executar todo fluxo automatizado de OAuth e retornar tokens."""
    try:
        # Executa Selenium, troca code por token e captura dados
        token_data = auto_authenticate()
        # Retorna apenas o access_token para simplicidade
        return (
            jsonify(
                {
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in"),
                }
            ),
            200,
        )
    except Exception as e:
        current_app.logger.error("Erro em auto-auth: %s", str(e))
        return jsonify({"error": str(e)}), getattr(e, "code", 500)


@conta_azul_bp.route("/callback")
def callback():
    """Endpoint de callback para receber apenas o authorization code."""
    error = request.args.get("error")
    if error:
        return jsonify({"error": error}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Parâmetro 'code' não fornecido"}), 400

    # Somente retorna o code, sem chamar get_tokens
    return jsonify({"code": code}), 200
