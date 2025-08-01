# app/__init__.py
"""
Flask application factory using dependency injection and SOLID principles.
"""

from flask import Flask

from .core.interfaces import IFlaskAppFactory, IConfigProvider, ILogger
from .core.container import container
from .routes import _webhook_routes, api_routes, conta_azul_routes
from .cli.sync_commands import sync_cli


class FlaskAppFactory(IFlaskAppFactory):
    """
    Flask application factory implementing IFlaskAppFactory.
    Follows Single Responsibility Principle - only creates Flask apps.
    """

    def __init__(self, config: IConfigProvider, logger: ILogger):
        self.config = config
        self.logger = logger

    def create_app(self) -> Flask:
        """Create and configure Flask application"""
        app = Flask(__name__)

        # Configure Flask
        self._configure_flask(app)

        # Setup logging
        if hasattr(self.logger, "configure"):
            self.logger.configure(app)

        # Register blueprints
        self._register_blueprints(app)

        # Register CLI commands
        self._register_cli_commands(app)

        # Validate configuration
        self._validate_configuration(app)

        return app

    def _configure_flask(self, app: Flask) -> None:
        """Configure Flask application settings"""
        # Convert config to dict for Flask
        config_dict = {
            "SECRET_KEY": self.config.get("SECRET_KEY"),
            "ENV": self.config.get("ENV"),
            "DEBUG": self.config.is_development(),
        }

        for key, value in config_dict.items():
            app.config[key] = value

    def _register_blueprints(self, app: Flask) -> None:
        """Register all application blueprints"""
        blueprints = [
            (api_routes.api_bp, "/api"),
            (_webhook_routes.webhook_bp, "/webhooks"),
            (conta_azul_routes.conta_azul_bp, "/conta-azul"),
        ]

        for blueprint, url_prefix in blueprints:
            app.register_blueprint(blueprint, url_prefix=url_prefix)

    def _register_cli_commands(self, app: Flask) -> None:
        """Register CLI commands"""
        app.cli.add_command(sync_cli)

    def _validate_configuration(self, app: Flask) -> None:
        """Validate configuration after app creation"""
        try:
            self.config.validate()
            self.logger.info("✅ Configuration validation successful")
        except EnvironmentError as e:
            self.logger.critical(f"❌ Configuration validation failed: {e}")
            raise


def create_app() -> Flask:
    """
    Main application factory function.
    Uses dependency injection container to resolve dependencies.
    """
    # Get dependencies from container
    config = container.resolve(IConfigProvider)
    logger = container.resolve(ILogger)

    # Create factory
    factory = FlaskAppFactory(config, logger)

    # Create and return app
    return factory.create_app()
