"""
API routes for data retrieval and processing.
"""
# app/routes/api_routes.py

from flask import Blueprint, jsonify
from app.services.webhook_services import validate_api_key

api_bp = Blueprint("api", __name__)


@api_bp.route("/data", methods=["GET"])
@validate_api_key
def get_data():
    """Retrieve sample data."""
    return jsonify({"status": "success", "data": "sample_data"})


@api_bp.route("/process", methods=["POST"])
@validate_api_key
def process_data():
    """Process incoming data."""
    # Lógica de processamento
    return jsonify({"status": "processed"}), 200
