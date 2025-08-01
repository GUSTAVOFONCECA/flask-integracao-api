# app/routes/__init__.py
"""
Pacote de rotas da aplicação.
"""
from .api_routes import api_bp
from ._webhook_routes import webhook_bp
from .conta_azul_routes import conta_azul_bp

__all__ = [
    "api_bp",
    "webhook_bp",
    "conta_azul_bp"
]
