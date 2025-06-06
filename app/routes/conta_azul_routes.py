# app/routes/conta_azul_routes.py
from flask import Blueprint, request, current_app, jsonify
from app.services.conta_azul_services import (
    get_tokens,
    set_tokens,
    get_sales,
    auto_authenticate,
)

conta_azul_bp = Blueprint("conta_azul", __name__, url_prefix="/conta-azul")


@conta_azul_bp.route("/auto-auth")
def auto_auth():
    """Endpoint para autenticação automática com Selenium"""
    try:
        token_data = auto_authenticate()
        return (
            jsonify(
                {
                    "status": "Autenticado automaticamente com sucesso!",
                    "access_token": token_data["access_token"],
                }
            ),
            200,
        )
    except RuntimeError as e:
        current_app.logger.error(
            f"Falha na autenticação automática (RuntimeError): {str(e)}"
        )
        return jsonify({"error": str(e)}), 500
    except KeyError as e:
        current_app.logger.error(
            f"Falha na autenticação automática (KeyError): {str(e)}"
        )
        return jsonify({"error": str(e)}), 400
    except ValueError as e:
        current_app.logger.error(
            f"Falha na autenticação automática (ValueError): {str(e)}"
        )
        return jsonify({"error": str(e)}), 400


@conta_azul_bp.route("/callback")
def callback():
    """Endpoint de callback para receber o código de autorização."""
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return jsonify({"error": error}), 400

    try:
        token_data = get_tokens(str(code))
        set_tokens(token_data)
        return jsonify({"status": "Autenticado com sucesso!"}), 200
    except ValueError as e:
        current_app.logger.error("Falha na autenticação (ValueError): %s", str(e))
        return jsonify({"error": str(e)}), 400
    except KeyError as e:
        current_app.logger.error("Falha na autenticação (KeyError): %s", str(e))
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        current_app.logger.error("Falha na autenticação (RuntimeError): %s", str(e))
        return jsonify({"error": str(e)}), 500


@conta_azul_bp.route("/vendas")
def vendas():
    """Endpoint para obter dados de vendas."""
    try:
        page = request.args.get("page", 1, type=int)
        size = request.args.get("size", 100, type=int)
        sales_data = get_sales(page, size)
        return jsonify(sales_data)
    except ValueError as e:
        current_app.logger.error("Erro de valor ao obter vendas: %s", str(e))
        return jsonify({"error": str(e)}), 400
    except KeyError as e:
        current_app.logger.error("Chave não encontrada ao obter vendas: %s", str(e))
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        current_app.logger.error("Erro de execução ao obter vendas: %s", str(e))
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        current_app.logger.error("Erro inesperado ao obter vendas: %s", str(e))
        raise  # Re-raise the exception to let Flask handle it or for further debugging
