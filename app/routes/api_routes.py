"""
API routes for data retrieval and processing.
"""

# app/routes/api_routes.py

from flask import Blueprint, jsonify
from app.config import Config
from app.services.bitrix24.bitrix_services import validate_api_key

api_bp = Blueprint("api", __name__)


@api_bp.route("/data/", methods=["GET"], strict_slashes=False)
@validate_api_key
def get_data():
    """Retrieve sample data."""
    return jsonify({"status": "success", "data": "sample_data"})


@api_bp.route("/health/", methods=["GET"], strict_slashes=False)
@validate_api_key
def health_check():
    """Endpoint para verificação de saúde da API"""
    return (
        jsonify({"status": "healthy", "version": "1.0.0", "environment": Config.ENV}),
        200,
    )
