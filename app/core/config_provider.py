# app/core/config_provider.py
"""
Configuration provider implementation following Single Responsibility Principle.
"""

import os
from typing import Any, Dict
from .interfaces import IConfigProvider


class EnvironmentConfigProvider(IConfigProvider):
    """Configuration provider that reads from environment variables"""

    def __init__(self):
        self._config_cache: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from environment"""
        # Digisac configuration
        self._config_cache.update(
            {
                "DIGISAC_USER": os.getenv("DIGISAC_USER"),
                "DIGISAC_PASSWORD": os.getenv("DIGISAC_PASSWORD"),
                "DIGISAC_TOKEN": os.getenv("DIGISAC_TOKEN"),
                "DIGISAC_USER_ID": os.getenv("DIGISAC_USER_ID"),
                # Conta Azul configuration
                "CONTA_AZUL_CLIENT_ID": os.getenv("CONTA_AZUL_CLIENT_ID"),
                "CONTA_AZUL_CLIENT_SECRET": os.getenv("CONTA_AZUL_CLIENT_SECRET"),
                "CONTA_AZUL_REDIRECT_URI": os.getenv("CONTA_AZUL_REDIRECT_URI"),
                "CONTA_AZUL_CONTA_BANCARIA_UUID": os.getenv(
                    "CONTA_AZUL_CONTA_BANCARIA_UUID"
                ),
                # Bitrix configuration
                "BITRIX_WEBHOOK_TOKEN": os.getenv("BITRIX_WEBHOOK_TOKEN"),
                # Application configuration
                "API_KEY": os.getenv("API_KEY"),
                "ENV": os.getenv("ENV", "development"),
                "SYNC_DATA_DIR": os.getenv("SYNC_DATA_DIR", "app/database"),
            }
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config_cache.get(key, default)

    def validate(self) -> None:
        """Validate required configuration"""
        required_keys = [
            "DIGISAC_USER",
            "DIGISAC_PASSWORD",
            "DIGISAC_TOKEN",
            "DIGISAC_USER_ID",
            "CONTA_AZUL_CLIENT_ID",
            "CONTA_AZUL_CLIENT_SECRET",
            "API_KEY",
        ]

        missing_keys = [key for key in required_keys if not self.get(key)]
        if missing_keys:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing_keys)}"
            )


class ServiceConfiguration:
    """Service-specific configuration following Open/Closed Principle"""

    DIGISAC_BASE_URL = "https://logicassessoria.digisac.chat/api/v1"
    CONTA_AZUL_TOKEN_URL = "https://auth.contaazul.com/oauth2/token"
    CONTA_AZUL_API_BASE_URL = "https://api-v2.contaazul.com"

    # Department IDs (could be moved to config later)
    CERT_DEPT_ID = "154521dc-71c0-4117-a697-bd978cd442aa"
    NO_BOT_DEPT_ID = "d9fe4658-1ad6-43ba-a00e-cf0b998852c2"

    # Service IDs for Conta Azul
    CERT_PJ_SERVICE_ID = "0b4f9a8b-01bb-4a89-93b3-7f56210bc75d"
    CERT_PF_SERVICE_ID = "586d5eb2-23aa-47ff-8157-fd85de8b9932"

    # Pricing
    CERT_PJ_PRICE = 185.0
    CERT_PF_PRICE = 130.0


"""
Configuration Provider following SOLID principles.
Implements Single Responsibility and Dependency Inversion.
"""

import os
import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class IConfigProvider(ABC):
    """Interface for configuration providers"""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        ...

    @abstractmethod
    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        ...

    @abstractmethod
    def items(self) -> Dict[str, Any]:
        """Get all configuration items"""
        ...


class EnvironmentConfigProvider(IConfigProvider):
    """
    Environment-based configuration provider.
    Follows Single Responsibility Principle.
    """

    def __init__(self):
        self._config = {}
        self._load_from_environment()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)

    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        value = self._config.get(key)
        if value is None:
            raise ValueError(f"Required configuration key '{key}' not found")
        return value

    def items(self) -> Dict[str, Any]:
        """Get all configuration items"""
        return self._config.copy()

    def _load_from_environment(self) -> None:
        """Load configuration from environment variables"""
        # Load common environment variables
        env_vars = [
            "DIGISAC_API_KEY",
            "CONTA_AZUL_CLIENT_ID",
            "CONTA_AZUL_CLIENT_SECRET",
            "BITRIX24_WEBHOOK_URL",
            "LOG_LEVEL",
            "DEBUG",
            "SECRET_KEY",
        ]

        for var in env_vars:
            value = os.getenv(var)
            if value is not None:
                self._config[var.lower()] = value

        # Set defaults
        self._config.setdefault("log_level", "INFO")
        self._config.setdefault("debug", False)

        logger.debug(f"Loaded {len(self._config)} configuration items")
