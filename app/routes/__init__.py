# app/routes/__init__.py
"""
Pacote de rotas da aplicação.
"""
from .api_routes import api_bp
from .webhook_routes import webhook_bp

__all__ = [
    "api_bp",
    "webhook_bp",
]
