# app/routes/webhook_routes.py

"""Arquivo principal de webhooks - mantido para compatibilidade."""

import logging
from flask import Blueprint

# Imports das rotas específicas
from .cnpj_routes import cnpj_bp
from .certificate_routes import certificate_bp
from .billing_routes import billing_bp
from .scheduling_routes import scheduling_bp

# Re-exportar blueprints para compatibilidade
webhook_bp = Blueprint("webhook_legacy", __name__)

logger = logging.getLogger(__name__)

# Estados válidos para negociações
VALID_STATUSES = [
    "pending",
    "info_sent",
    "customer_retention",
    "sale_created",
    "billing_generated",
    "billing_pdf_sent",
    "scheduling_form_sent",
    "complete",
]

def handle_renewal_request():
    """Handle renewal request - wrapper for certificate alert webhook"""
    from .certificate_routes import envia_comunicado_para_cliente_certif_digital_digisac
    return envia_comunicado_para_cliente_certif_digital_digisac()

# Registrar todos os blueprints
def register_webhook_blueprints(app):
    """Registrar todos os blueprints de webhook na aplicação."""
    app.register_blueprint(cnpj_bp, url_prefix="/webhook")
    app.register_blueprint(certificate_bp, url_prefix="/webhook")
    app.register_blueprint(billing_bp, url_prefix="/webhook")
    app.register_blueprint(scheduling_bp, url_prefix="/webhook")