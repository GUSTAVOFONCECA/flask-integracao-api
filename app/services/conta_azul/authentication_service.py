# app/services/conta_azul/authentication_service.py
"""
Conta Azul authentication service following Single Responsibility Principle.
"""

import base64
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import requests

from app.core.interfaces import IAuthenticationService, ITokenManager, IConfigProvider
from app.core.config_provider import ServiceConfiguration


logger = logging.getLogger(__name__)


class ContaAzulTokenManager(ITokenManager):
    """Token manager for Conta Azul following SRP"""

    def __init__(self, tokens_file_path: str):
        self.tokens_file_path = tokens_file_path
        self.tokens = {
            "access_token": None,
            "refresh_token": None,
            "id_token": None,
            "expires_at": None,
        }
        os.makedirs(os.path.dirname(tokens_file_path), exist_ok=True)
        self.load_tokens()

    def save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to file"""
        data = tokens.copy()
        if isinstance(data.get("expires_at"), datetime):
            data["expires_at"] = data["expires_at"].isoformat()

        with open(self.tokens_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info("Conta Azul tokens saved to file: %s", self.tokens_file_path)

    def load_tokens(self) -> Dict[str, Any]:
        """Load tokens from file"""
        if os.path.exists(self.tokens_file_path):
            with open(self.tokens_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.tokens["access_token"] = data.get("access_token")
                self.tokens["refresh_token"] = data.get("refresh_token")
                self.tokens["id_token"] = data.get("id_token")
                expires_at = data.get("expires_at")
                if expires_at:
                    self.tokens["expires_at"] = datetime.fromisoformat(expires_at)
        return self.tokens

    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        return {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Content-Type": "application/json",
        }


class ContaAzulAuthenticationService(IAuthenticationService):
    """Conta Azul authentication service following SRP and DIP"""

    REFRESH_MARGIN_SECONDS = 300  # 5 minutes safety margin

    def __init__(self, config: IConfigProvider, token_manager: ITokenManager):
        self.config = config
        self.token_manager = token_manager

    def authenticate(self) -> Dict[str, Any]:
        """Authenticate using authorization code (requires Selenium automation)"""
        from app.services.conta_azul.conta_azul_auto_auth import automate_auth

        # Get authorization code via Selenium
        auth_code = automate_auth()

        # Exchange code for tokens
        token_data = self._exchange_code_for_tokens(auth_code)
        self._update_tokens(token_data)
        return token_data

    def refresh_tokens(self) -> Dict[str, Any]:
        """Refresh tokens using refresh token"""
        tokens = self.token_manager.load_tokens()
        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            raise ValueError("No refresh token available")

        credentials = f"{self.config.get('CONTA_AZUL_CLIENT_ID')}:{self.config.get('CONTA_AZUL_CLIENT_SECRET')}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }

        body = (
            f"client_id={self.config.get('CONTA_AZUL_CLIENT_ID')}"
            f"&client_secret={self.config.get('CONTA_AZUL_CLIENT_SECRET')}"
            f"&grant_type=refresh_token"
            f"&code={refresh_token}"
        )

        response = requests.post(
            ServiceConfiguration.CONTA_AZUL_TOKEN_URL,
            data=body,
            headers=headers,
            timeout=60,
        )

        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            raise Exception("Token refresh failed")

        token_data = response.json()
        self._update_tokens(token_data)
        return token_data

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        tokens = self.token_manager.load_tokens()
        access_token = tokens.get("access_token")

        if not access_token:
            return False

        delay = self._get_token_expiry_delay()
        if delay is None or delay <= 0:
            try:
                self.refresh_tokens()
                return True
            except Exception as e:
                logger.error("Failed to refresh token: %s", e)
                return False

        return True

    def refresh_tokens_safe(self) -> Dict[str, Any]:
        """Safely refresh tokens with automatic fallback to re-authentication"""
        delay = self._get_token_expiry_delay()
        logger.info(f"⏱️ Token time remaining: {delay:.0f} seconds")

        if delay is None or delay < 0:
            logger.warning("⚠️ Token expired — trying auto_authenticate")
            return self.authenticate()

        if delay <= self.REFRESH_MARGIN_SECONDS:
            try:
                logger.info("🔁 Token about to expire — refreshing with refresh_token")
                return self.refresh_tokens()
            except Exception as e:
                logger.error(
                    f"❌ Error refreshing token — trying auto_authenticate: {e}"
                )
                return self.authenticate()

        logger.info("✅ Token still valid — no action needed")
        return self.token_manager.load_tokens()

    def _exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""
        credentials = f"{self.config.get('CONTA_AZUL_CLIENT_ID')}:{self.config.get('CONTA_AZUL_CLIENT_SECRET')}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }

        body = (
            f"client_id={self.config.get('CONTA_AZUL_CLIENT_ID')}"
            f"&client_secret={self.config.get('CONTA_AZUL_CLIENT_SECRET')}"
            f"&grant_type=authorization_code"
            f"&code={code}"
            f"&redirect_uri={self.config.get('CONTA_AZUL_REDIRECT_URI')}"
        )

        response = requests.post(
            ServiceConfiguration.CONTA_AZUL_TOKEN_URL,
            data=body,
            headers=headers,
            timeout=60,
        )

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            raise Exception("Token exchange failed")

        return response.json()

    def _update_tokens(self, token_data: Dict[str, Any]) -> None:
        """Update tokens in manager"""
        tokens = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "id_token": token_data.get("id_token"),
            "expires_at": datetime.now() + timedelta(seconds=token_data["expires_in"]),
        }
        self.token_manager.save_tokens(tokens)

    def _get_token_expiry_delay(self) -> float:
        """Get time remaining until token expiry"""
        tokens = self.token_manager.load_tokens()
        expires_at = tokens.get("expires_at")

        if not isinstance(expires_at, datetime):
            return None

        delay = (expires_at - datetime.now()).total_seconds()
        return max(delay, 0)
