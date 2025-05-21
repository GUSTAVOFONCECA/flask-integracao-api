# app/__init__.py
from flask import Flask
from flask_talisman import Talisman # type: ignore
from app.config import Config, configure_logging
from app.routes import api_routes, webhook_routes


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Configurar logging
    configure_logging(app)

    # Registrar blueprints
    app.register_blueprint(api_routes.api_bp, url_prefix="/api")
    app.register_blueprint(webhook_routes.webhook_bp, url_prefix="/webhooks")

    # Validar configuração
    try:
        Config.validate()
    except EnvironmentError as e:
        app.logger.critical("%s", str(e))
        raise

    return app
