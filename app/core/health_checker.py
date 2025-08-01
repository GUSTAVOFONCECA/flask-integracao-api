# app/core/health_checker.py

"""
Health checker implementation following SOLID principles.
"""

import logging
import requests
from typing import Dict, Any, List
from datetime import datetime

from app.core.interfaces import IHealthChecker, IConfigProvider

logger = logging.getLogger(__name__)


class HealthChecker(IHealthChecker):
    """
    Health checker implementation following Single Responsibility Principle.
    Only responsible for checking system health.
    """

    def __init__(self, flask_app, config: IConfigProvider):
        self.flask_app = flask_app
        self.config = config
        self.last_check_time = None
        self.last_check_results = {}

    def check_health(self) -> Dict[str, Any]:
        """Check overall system health"""
        health_results = {
            "healthy": True,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
        }

        # Perform individual health checks
        checks = [
            ("database", self._check_database_health),
            ("configuration", self._check_configuration_health),
            ("external_apis", self._check_external_apis_health),
            ("flask_app", self._check_flask_app_health),
        ]

        for check_name, check_function in checks:
            try:
                result = check_function()
                health_results["checks"][check_name] = result

                if not result.get("healthy", False):
                    health_results["healthy"] = False

            except Exception as e:
                logger.error(f"Health check '{check_name}' failed: {e}")
                health_results["checks"][check_name] = {
                    "healthy": False,
                    "error": str(e),
                }
                health_results["healthy"] = False

        self.last_check_time = datetime.utcnow()
        self.last_check_results = health_results

        return health_results

    def is_healthy(self) -> bool:
        """Check if system is currently healthy"""
        health_status = self.check_health()
        return health_status.get("healthy", False)

    def check_dependencies(self) -> Dict[str, bool]:
        """Check critical dependencies"""
        dependencies = {
            "database": self._check_database_connectivity(),
            "configuration": self._check_required_config(),
            "flask_app": self._check_flask_app_ready(),
        }

        return dependencies

    def check_api_health(self) -> bool:
        """Check if API is ready to serve requests"""
        try:
            # Check if Flask app is configured correctly
            if not self.flask_app:
                return False

            # Check if required configuration is present
            if not self._check_required_config():
                return False

            # Check database connectivity
            if not self._check_database_connectivity():
                return False

            return True

        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return False

    def _check_database_health(self) -> Dict[str, Any]:
        """Check database health"""
        try:
            from app.database.database import get_db_connection

            with get_db_connection() as conn:
                # Simple query to test connection
                cursor = conn.execute("SELECT 1")
                cursor.fetchone()

            return {
                "healthy": True,
                "status": "connected",
                "checked_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat(),
            }

    def _check_configuration_health(self) -> Dict[str, Any]:
        """Check configuration health"""
        try:
            self.config.validate()

            return {
                "healthy": True,
                "status": "valid",
                "checked_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            return {
                "healthy": False,
                "status": "invalid",
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat(),
            }

    def _check_external_apis_health(self) -> Dict[str, Any]:
        """Check external APIs health"""
        api_checks = {}
        overall_healthy = True

        # Check Bitrix24 API
        try:
            bitrix_url = self.config.get("BITRIX_WEBHOOK_URL")
            if bitrix_url:
                # Simple ping to check connectivity
                response = requests.head(bitrix_url, timeout=5)
                api_checks["bitrix24"] = {
                    "healthy": response.status_code < 500,
                    "status_code": response.status_code,
                }
            else:
                api_checks["bitrix24"] = {
                    "healthy": False,
                    "error": "URL not configured",
                }
        except Exception as e:
            api_checks["bitrix24"] = {"healthy": False, "error": str(e)}
            overall_healthy = False

        return {
            "healthy": overall_healthy,
            "apis": api_checks,
            "checked_at": datetime.utcnow().isoformat(),
        }

    def _check_flask_app_health(self) -> Dict[str, Any]:
        """Check Flask app health"""
        try:
            if not self.flask_app:
                return {"healthy": False, "error": "Flask app not initialized"}

            # Check if app has required blueprints
            blueprint_count = len(self.flask_app.blueprints)

            return {
                "healthy": True,
                "status": "running",
                "blueprints_count": blueprint_count,
                "checked_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat(),
            }

    def _check_database_connectivity(self) -> bool:
        """Simple database connectivity check"""
        try:
            from app.database.database import get_db_connection

            with get_db_connection() as conn:
                cursor = conn.execute("SELECT 1")
                cursor.fetchone()
            return True

        except Exception as e:
            logger.error(f"Database connectivity check failed: {e}")
            return False

    def _check_required_config(self) -> bool:
        """Check if required configuration is present"""
        try:
            self.config.validate()
            return True
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False

    def _check_flask_app_ready(self) -> bool:
        """Check if Flask app is ready"""
        return self.flask_app is not None
