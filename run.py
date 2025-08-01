# run.py
"""
Main application entry point using SOLID principles and dependency injection.
"""

import sys
import logging
from threading import Thread

from app.config import Config
from app.core.interfaces import IConfigProvider, ILogger
from app.core.container import container
from app.core.lifecycle import ApplicationLifecycle
from app.core.health_checker import HealthChecker
from app.core.logging_service import FlaskLogger
from app.services.tunnel_service import TunnelService
from app.workers.ticket_flow_worker import TicketFlowWorker
from app.workers.session_worker import SessionWorker
from app.workers.token_refresh_worker import TokenRefreshWorker
from app.database.database import init_db
from app import create_app

# Setup basic logging first
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ApplicationBootstrapper:
    """
    Application bootstrapper following Single Responsibility Principle.
    Only responsible for dependency registration and app initialization.
    """

    def __init__(self):
        self.lifecycle = ApplicationLifecycle()

    def bootstrap(self) -> ApplicationLifecycle:
        """Bootstrap the application with all dependencies"""

        # 1. Register core dependencies
        self._register_core_dependencies()

        # 2. Initialize database
        self._initialize_database()

        # 3. Create Flask app
        flask_app = create_app()

        # 4. Register application services
        self._register_application_services(flask_app)

        # 5. Register workers
        self._register_workers(flask_app)

        # 6. Register Flask server
        self._register_flask_server(flask_app)

        return self.lifecycle

    def _register_core_dependencies(self) -> None:
        """Register core infrastructure dependencies"""
        # Configuration
        config = Config()
        container.register_instance(IConfigProvider, config)

        # Logging
        logger_service = FlaskLogger(config)
        container.register_instance(ILogger, logger_service)

    def _initialize_database(self) -> None:
        """Initialize database"""
        init_db()
        logger_service = container.resolve(ILogger)
        logger_service.info("✅ Database initialized")

    def _register_application_services(self, flask_app) -> None:
        """Register application-level services"""
        config = container.resolve(IConfigProvider)

        # Health checker
        health_checker = HealthChecker(flask_app, config)
        self.lifecycle.set_health_checker(health_checker)
        self.lifecycle.register_service(health_checker)

        # Tunnel service
        tunnel_service = TunnelService(config)
        container.register_instance("tunnel_service", tunnel_service)
        self.lifecycle.register_service(tunnel_service)

    def _register_workers(self, flask_app) -> None:
        """Register background workers"""
        # Create workers with Flask app context
        workers = [
            TicketFlowWorker(flask_app),
            SessionWorker(flask_app),
            TokenRefreshWorker(flask_app),
        ]

        for worker in workers:
            self.lifecycle.register_worker(worker)

    def _register_flask_server(self, flask_app) -> None:
        """Register Flask server as a service"""
        config = container.resolve(IConfigProvider)
        flask_server = FlaskServerService(flask_app, config)
        container.register_instance("flask_server", flask_server)
        self.lifecycle.register_service(flask_server)


class FlaskServerService:
    """
    Flask server wrapped as a service for lifecycle management.
    """

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.server_thread = None

    def initialize(self) -> None:
        """Initialize Flask server"""
        logger_service = container.resolve(ILogger)
        logger_service.info("✅ Flask server initialized")

    def start_server(self) -> None:
        """Start Flask server"""
        logger_service = container.resolve(ILogger)

        if self.config.is_production():
            logger_service.info("🚀 Starting server in production mode")
            try:
                from waitress import serve

                serve(self.app, host="0.0.0.0", port=self.config.get("TUNNEL_PORT"))
            except ImportError:
                logger_service.warning("Waitress not available, using Flask dev server")
                self.app.run(
                    host="0.0.0.0",
                    port=self.config.get("TUNNEL_PORT"),
                    debug=False,
                    use_reloader=False,
                )
        else:
            logger_service.info("🚀 Starting server in development mode")
            self.app.run(
                host="0.0.0.0",
                port=self.config.get("TUNNEL_PORT"),
                debug=True,
                use_reloader=False,
            )

    def cleanup(self) -> None:
        """Cleanup server resources"""
        pass


def main() -> None:
    """Main entry point"""
    try:
        # Bootstrap application
        bootstrapper = ApplicationBootstrapper()
        lifecycle = bootstrapper.bootstrap()

        # Initialize lifecycle
        lifecycle.initialize()

        # Get logger and health checker
        logger_service = container.resolve(ILogger)

        # Perform basic health checks
        if hasattr(lifecycle, "health_checker") and lifecycle.health_checker:
            health_results = lifecycle.health_checker.check_dependencies()
            failed_checks = [
                name for name, healthy in health_results.items() if not healthy
            ]

            if failed_checks:
                logger_service.error(f"❌ Health checks failed: {failed_checks}")
                # Continue anyway in development
                if not container.resolve(IConfigProvider).is_development():
                    sys.exit(1)

        logger_service.info("✅ All health checks passed")

        # Start tunnel service
        try:
            tunnel_service = container.resolve("tunnel_service")
            tunnel_service.start()
        except Exception as e:
            logger_service.warning(f"⚠️ Could not start tunnel service: {e}")

        # Start background workers
        lifecycle.start_workers()

        # Start Flask server
        flask_server = container.resolve("flask_server")
        logger_service.info("🎉 Application started successfully")

        # Run Flask server directly
        flask_server.start_server()

    except Exception as e:
        if "logger_service" in locals():
            logger_service.critical(f"💥 Application startup failed: {e}")
        else:
            print(f"CRITICAL: Application startup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
