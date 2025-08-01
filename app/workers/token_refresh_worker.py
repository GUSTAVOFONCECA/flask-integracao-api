# app/workers/token_refresh_worker.py
"""
Token Refresh Worker following SOLID principles.
Implements Single Responsibility and Dependency Inversion.
"""

import time
import logging
from typing import Protocol
from abc import ABC, abstractmethod

from app.core.interfaces import IWorker, ILogger, ITokenManager
from app.utils.utils import debug


class ITokenRefreshService(Protocol):
    """Interface for token refresh operations"""

    def refresh_tokens_safely(self) -> bool:
        """Refresh tokens safely"""
        ...

    def get_token_expiry_time(self) -> int:
        """Get time until token expires in seconds"""
        ...


class TokenRefreshWorker(IWorker):
    """
    Worker responsible for automatic token refresh.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        token_service: ITokenRefreshService,
        logger: ILogger,
        interval_seconds: int = 600,
    ):
        self._token_service = token_service
        self._logger = logger
        self._interval_seconds = interval_seconds
        self._running = False

    @debug
    def start(self) -> None:
        """Start the token refresh worker"""
        self._running = True
        self._logger.info(
            f"🔑 Starting token refresh worker (interval: {self._interval_seconds}s)"
        )

        while self._running:
            try:
                self._refresh_tokens()
            except Exception as e:
                self._logger.error(f"Error in token refresh worker: {e}")

            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        """Stop the token refresh worker"""
        self._running = False
        self._logger.info("🛑 Token refresh worker stopped")

    @debug
    def _refresh_tokens(self) -> None:
        """Refresh tokens if needed"""
        try:
            expiry_time = self._token_service.get_token_expiry_time()

            # Refresh if token expires in less than 10 minutes
            if expiry_time < 600:
                self._logger.info(f"🔄 Token expires in {expiry_time}s, refreshing...")
                success = self._token_service.refresh_tokens_safely()

                if success:
                    self._logger.info("✅ Token refreshed successfully")
                else:
                    self._logger.warning("⚠️ Token refresh failed")
            else:
                self._logger.debug(f"🔑 Token valid for {expiry_time}s")

        except Exception as e:
            self._logger.error(f"❌ Error during token refresh: {e}")


# Factory function for creating token refresh worker
def create_token_refresh_worker(
    token_service: ITokenRefreshService, logger: ILogger, interval_seconds: int = 600
) -> TokenRefreshWorker:
    """Factory function for creating token refresh worker"""
    return TokenRefreshWorker(token_service, logger, interval_seconds)
