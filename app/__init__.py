# app/__init__.py

"""
Inicializa o app
"""

from flask import Flask
from app.config import Config, configure_logging
from app.routes import api_routes, webhook_routes, conta_azul_routes


def create_app() -> Flask:
    """Fábrica de aplicação Flask para inicialização e configuração do sistema.

    Responsável por:
    - Criar e configurar a instância do Flask
    - Registrar blueprints de rotas
    - Configurar sistema de logging
    - Validar variáveis de ambiente

    :return: Instância do aplicativo Flask configurado
    :rtype: Flask
    :raises EnvironmentError: Se variáveis de ambiente obrigatórias estiverem faltando

    .. rubric:: Exemplo de Uso

    .. code-block:: python

        from app import create_app
        app = create_app()

        if __name__ == '__main__':
            app.run()

    .. rubric:: Fluxo de Inicialização

    1. Cria instância do Flask
    2. Carrega configurações da classe Config
    3. Configura sistema de logging
    4. Registra endpoints (API e Webhooks)
    5. Valida configurações essenciais
    """
    app = Flask(__name__)

    # Configuração básica do aplicativo
    _configure_app(app)

    # Configuração avançada
    _register_blueprints(app)
    _perform_post_configuration(app)

    return app


def _configure_app(app: Flask) -> None:
    """Configurações iniciais do aplicativo Flask."""
    app.config.from_object(Config)
    configure_logging(app)


def _register_blueprints(app: Flask) -> None:
    """Registra todos os blueprints de rotas."""
    blueprints = [
        (api_routes.api_bp, "/api"),
        (webhook_routes.webhook_bp, "/webhooks"),
        (conta_azul_routes.conta_azul_bp, "/conta-azul"),  # Novo blueprint
    ]

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)


def _perform_post_configuration(app: Flask) -> None:
    """Validações e configurações pós-inicialização."""
    try:
        Config.validate()
    except EnvironmentError as e:
        app.logger.critical("Falha na validação de configuração: %s", str(e))
        raise
