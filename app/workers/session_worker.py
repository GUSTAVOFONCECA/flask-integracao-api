# app/workers/session_worker.py
"""
Session Worker following SOLID principles.
Implements Single Responsibility and Dependency Inversion.
"""

import time
import logging
from typing import Protocol
from abc import ABC, abstractmethod

from app.core.interfaces import IWorker, ILogger
from app.services.renewal_services import SessionManager
from app.utils.utils import debug


class ISessionService(Protocol):
    """Interface for session service operations"""

    def check_expired_sessions(self) -> list:
        """Check for expired sessions"""
        ...

    def finalize_session(self, contact_number: str) -> bool:
        """Finalize a session"""
        ...


class SessionWorker(IWorker):
    """
    Worker responsible for managing session lifecycle.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        session_service: ISessionService,
        logger: ILogger,
        interval_seconds: int = 60,
    ):
        self._session_service = session_service
        self._logger = logger
        self._interval_seconds = interval_seconds
        self._running = False

    @debug
    def start(self) -> None:
        """Start the session worker"""
        self._running = True
        self._logger.info(
            f"🔁 Starting session worker (interval: {self._interval_seconds}s)"
        )

        while self._running:
            try:
                self._process_expired_sessions()
            except Exception as e:
                self._logger.error(f"Error in session worker: {e}")

            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        """Stop the session worker"""
        self._running = False
        self._logger.info("🛑 Session worker stopped")

    @debug
    def _process_expired_sessions(self) -> None:
        """Process expired sessions"""
        expired_sessions = self._session_service.check_expired_sessions()

        if expired_sessions:
            self._logger.info(f"🔍 Processing {len(expired_sessions)} expired sessions")

        for session in expired_sessions:
            contact_number = session.get("contact_number")
            if contact_number:
                self._logger.info(f"⏳ Finalizing expired session for {contact_number}")
                try:
                    self._session_service.finalize_session(contact_number)
                except Exception as e:
                    self._logger.error(
                        f"Error finalizing session {contact_number}: {e}"
                    )


# Factory function for creating session worker
def create_session_worker(
    session_service: ISessionService, logger: ILogger, interval_seconds: int = 60
) -> SessionWorker:
    """Factory function for creating session worker"""
    return SessionWorker(session_service, logger, interval_seconds)
