# app/services/digisac/authentication_service.py
"""
Digisac authentication service following Single Responsibility Principle.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import requests

from app.core.interfaces import IAuthenticationService, ITokenManager, IConfigProvider
from app.core.config_provider import ServiceConfiguration


logger = logging.getLogger(__name__)


class DigisacTokenManager(ITokenManager):
    """Token manager for Digisac following SRP"""

    def __init__(self, tokens_file_path: str):
        self.tokens_file_path = tokens_file_path
        self.tokens = {"access_token": None, "refresh_token": None, "expires_at": None}
        os.makedirs(os.path.dirname(tokens_file_path), exist_ok=True)
        self.load_tokens()

    def save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to file"""
        data = tokens.copy()
        if isinstance(data.get("expires_at"), datetime):
            data["expires_at"] = data["expires_at"].isoformat()

        with open(self.tokens_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_tokens(self) -> Dict[str, Any]:
        """Load tokens from file"""
        if os.path.exists(self.tokens_file_path):
            with open(self.tokens_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k in ("access_token", "refresh_token"):
                    self.tokens[k] = data.get(k)
                exp = data.get("expires_at")
                self.tokens["expires_at"] = datetime.fromisoformat(exp) if exp else None
        return self.tokens

    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        return {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Content-Type": "application/json",
        }


class DigisacAuthenticationService(IAuthenticationService):
    """Digisac authentication service following SRP and DIP"""

    def __init__(self, config: IConfigProvider, token_manager: ITokenManager):
        self.config = config
        self.token_manager = token_manager
        self.client_id = "api"
        self.client_secret = "secret"

    def authenticate(self) -> Dict[str, Any]:
        """Authenticate with username/password"""
        url = f"{ServiceConfiguration.DIGISAC_BASE_URL}/oauth/token"
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.config.get("DIGISAC_USER"),
            "password": self.config.get("DIGISAC_PASSWORD"),
        }

        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            self._update_tokens(token_data)
            return token_data
        except requests.exceptions.RequestException as e:
            logger.error("Authentication failed: %s", str(e))
            raise

    def refresh_tokens(self) -> Dict[str, Any]:
        """Refresh tokens using refresh token"""
        tokens = self.token_manager.load_tokens()
        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            return self.authenticate()

        url = f"{ServiceConfiguration.DIGISAC_BASE_URL}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        try:
            response = requests.post(url, data=payload, timeout=60)
            response.raise_for_status()
            token_data = response.json()
            self._update_tokens(token_data)
            return token_data
        except requests.exceptions.RequestException as e:
            logger.error("Token refresh failed: %s", str(e))
            return self.authenticate()

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        tokens = self.token_manager.load_tokens()
        access_token = tokens.get("access_token")
        expires_at = tokens.get("expires_at")

        if not access_token:
            return False

        if expires_at and datetime.utcnow() > expires_at:
            try:
                self.refresh_tokens()
                return True
            except Exception:
                return False

        return True

    def _update_tokens(self, token_data: Dict[str, Any]) -> None:
        """Update tokens in manager"""
        tokens = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": datetime.utcnow()
            + timedelta(seconds=token_data["expires_in"] - 60),
        }
        self.token_manager.save_tokens(tokens)
