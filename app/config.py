# app/config.py
"""
Configuration provider implementing SOLID principles.
Separated from logging configuration for Single Responsibility.
"""

import os
from typing import Any, List
from dotenv import load_dotenv
from .core.interfaces import IConfigProvider

# Load environment variables
load_dotenv()


class Config(IConfigProvider):
    """
    Configuration provider following Single Responsibility Principle.
    Only handles configuration loading and validation.
    """

    def __init__(self):
        # Environment
        self.ENV: str = os.getenv("FLASK_ENV", "production").lower()

        # Directories
        self.PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.SYNC_DATA_DIR = os.path.join(self.PROJECT_ROOT, "app", "database")
        self.SYNC_LOG_DIR = os.path.join(self.PROJECT_ROOT, "logs")

        # Core settings
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "")
        self.WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
        self.API_KEY: str = os.getenv("API_KEY", "")
        self.TUNNEL_PORT: int = int(os.getenv("TUNNEL_PORT", "5478"))

        # Bitrix24
        self.BITRIX_WEBHOOK_URL: str = os.getenv("BITRIX_WEBHOOK_URL", "")
        self.BITRIX_WEBHOOK_TOKEN: str = os.getenv("BITRIX_WEBHOOK_TOKEN", "")

        # Digisac
        self.DIGISAC_USER: str = os.getenv("DIGISAC_USER", "")
        self.DIGISAC_PASSWORD: str = os.getenv("DIGISAC_PASSWORD", "")
        self.DIGISAC_USER_ID: str = os.getenv("DIGISAC_USER_ID", "")
        self.DIGISAC_TOKEN: str = os.getenv("DIGISAC_TOKEN", "")

        # Conta Azul
        self.CONTA_AZUL_CLIENT_ID: str = os.getenv("CONTA_AZUL_CLIENT_ID", "")
        self.CONTA_AZUL_CLIENT_SECRET: str = os.getenv("CONTA_AZUL_CLIENT_SECRET", "")
        self.CONTA_AZUL_REDIRECT_URI: str = os.getenv(
            "CONTA_AZUL_REDIRECT_URI", "https://127.0.0.1:5478/conta-azul/callback"
        )
        self.CONTA_AZUL_EMAIL: str = os.getenv("CONTA_AZUL_EMAIL", "")
        self.CONTA_AZUL_PASSWORD: str = os.getenv("CONTA_AZUL_PASSWORD", "")
        self.CONTA_AZUL_CONTA_BANCARIA_UUID: str = os.getenv(
            "CONTA_AZUL_CONTA_BANCARIA_UUID", ""
        )

        # Runtime
        self.TUNNEL_PUBLIC_IP: str = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        return getattr(self, key, default)

    def get_required(self, key: str) -> Any:
        """Get required configuration value"""
        value = self.get(key)
        if value is None:
            raise EnvironmentError(f"Required configuration '{key}' not found")
        return value

    def has(self, key: str) -> bool:
        """Check if configuration key exists"""
        return hasattr(self, key) and getattr(self, key) is not None

    def validate(self) -> None:
        """Validate required configuration values"""
        required_fields = ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]
        missing = [field for field in required_fields if not getattr(self, field)]

        if missing:
            raise EnvironmentError(
                f"Required configuration missing: {', '.join(missing)}"
            )

    def get_required_fields(self) -> List[str]:
        """Get list of required configuration fields"""
        return ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]

    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.ENV == "development"

    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENV == "production"
