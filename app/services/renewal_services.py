# app/services/renewal_services.py
"""
Renewal Services following SOLID principles.
Implements Single Responsibility, Open/Closed, and Dependency Inversion.
"""

import logging
import json
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Protocol
from abc import ABC, abstractmethod

from app.database.database import get_db_connection
from app.utils.utils import standardize_phone_number, debug


logger = logging.getLogger(__name__)


# Domain Models
class PendingRenewal:
    """Domain model for pending renewal"""

    def __init__(
        self,
        company_name: str,
        document: str,
        contact_number: str,
        contact_name: str,
        deal_type: str,
        spa_id: int,
        status: str,
        created_at: Optional[datetime] = None,
        last_interaction: Optional[datetime] = None,
        is_processing: bool = False,
    ):
        self.company_name = company_name
        self.document = document
        self.contact_number = standardize_phone_number(contact_number)
        self.contact_name = contact_name
        self.deal_type = deal_type
        self.spa_id = spa_id
        self.status = status
        self.created_at = created_at or datetime.now()
        self.last_interaction = last_interaction
        self.is_processing = is_processing

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "company_name": self.company_name,
            "document": self.document,
            "contact_number": self.contact_number,
            "contact_name": self.contact_name,
            "deal_type": self.deal_type,
            "spa_id": self.spa_id,
            "status": self.status,
            "created_at": self.created_at,
            "last_interaction": self.last_interaction,
            "is_processing": self.is_processing,
        }


class ContactSession:
    """Domain model for contact session"""

    def __init__(
        self,
        contact_number: str,
        expected_commands: int,
        received_commands: int = 0,
        status: str = "active",
        created_at: Optional[datetime] = None,
        session_id: Optional[int] = None,
    ):
        self.contact_number = standardize_phone_number(contact_number)
        self.expected_commands = expected_commands
        self.received_commands = received_commands
        self.status = status
        self.created_at = created_at or datetime.now()
        self.session_id = session_id

    def is_complete(self) -> bool:
        """Check if session is complete"""
        return self.received_commands >= self.expected_commands

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session is expired"""
        if not self.created_at:
            return False

        elapsed = datetime.now() - self.created_at
        return elapsed >= timedelta(minutes=timeout_minutes)


# Repository Interfaces
class IPendingRenewalRepository(Protocol):
    """Repository interface for pending renewals"""

    def add(self, renewal: PendingRenewal) -> str:
        """Add pending renewal"""
        ...

    def update(self, spa_id: int, **kwargs) -> bool:
        """Update pending renewal"""
        ...

    def get_by_contact(
        self, contact_number: str, context_aware: bool = False
    ) -> Optional[PendingRenewal]:
        """Get pending renewal by contact"""
        ...

    def get_by_spa_id(self, spa_id: int) -> Optional[PendingRenewal]:
        """Get pending renewal by SPA ID"""
        ...

    def get_all_by_contact(self, contact_number: str) -> List[PendingRenewal]:
        """Get all pending renewals by contact"""
        ...


class ISessionRepository(Protocol):
    """Repository interface for sessions"""

    def create_session(self, session: ContactSession) -> ContactSession:
        """Create new session"""
        ...

    def get_active_session(self, contact_number: str) -> Optional[ContactSession]:
        """Get active session"""
        ...

    def update_session(self, session: ContactSession) -> bool:
        """Update session"""
        ...

    def get_expired_sessions(self, timeout_minutes: int) -> List[ContactSession]:
        """Get expired sessions"""
        ...


class IMessageQueueRepository(Protocol):
    """Repository interface for message queue"""

    def add_message(self, spa_id: int, payload: Dict[str, Any]) -> int:
        """Add message to queue"""
        ...

    def get_pending_messages(self, spa_id: int) -> List[Dict[str, Any]]:
        """Get pending messages"""
        ...

    def mark_message_processed(self, message_id: int) -> bool:
        """Mark message as processed"""
        ...


# Repository Implementations
class SQLitePendingRenewalRepository(IPendingRenewalRepository):
    """SQLite implementation of pending renewal repository"""

    @debug
    def add(self, renewal: PendingRenewal) -> str:
        """Add pending renewal"""
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO certif_pending_renewals (
                        company_name, document, contact_number, contact_name, 
                        deal_type, spa_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(spa_id) DO UPDATE SET
                        company_name = excluded.company_name,
                        document = excluded.document,
                        contact_number = excluded.contact_number,
                        contact_name = excluded.contact_name,
                        deal_type = excluded.deal_type,
                        status = excluded.status
                    """,
                    (
                        renewal.company_name,
                        renewal.document,
                        renewal.contact_number,
                        renewal.contact_name,
                        renewal.deal_type,
                        renewal.spa_id,
                        renewal.status,
                    ),
                )
                conn.commit()
            return renewal.contact_number
        except Exception as e:
            logger.error(f"Error adding pending renewal: {str(e)}")
            raise

    @debug
    def update(self, spa_id: int, **kwargs) -> bool:
        """Update pending renewal"""
        if not isinstance(spa_id, int):
            try:
                spa_id = int(spa_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid SPA ID: {spa_id}")
                return False

        update_fields = {"last_interaction": datetime.now()}
        update_fields.update(kwargs)

        set_clauses = [f"{field} = ?" for field in update_fields.keys()]
        params = list(update_fields.values())
        params.append(spa_id)

        sql = f"UPDATE certif_pending_renewals SET {', '.join(set_clauses)} WHERE spa_id = ?"

        try:
            with get_db_connection() as conn:
                cur = conn.execute(sql, tuple(params))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating SPA {spa_id}: {e}")
            raise

    @debug
    def get_by_contact(
        self, contact_number: str, context_aware: bool = False
    ) -> Optional[PendingRenewal]:
        """Get pending renewal by contact"""
        std_number = standardize_phone_number(contact_number)

        query = """
            SELECT * FROM certif_pending_renewals
            WHERE contact_number = ?
            AND status NOT IN ('customer_retention', 'scheduling_form_sent', 'complete')
            ORDER BY {}
            LIMIT 1
        """

        if context_aware:
            final_query = query.format(
                """
                CASE WHEN last_interaction IS NULL THEN 0 ELSE 1 END, 
                last_interaction ASC
                """
            )
        else:
            final_query = query.format("created_at DESC")

        with get_db_connection() as conn:
            row = conn.execute(final_query, (std_number,)).fetchone()
            if row:
                return self._row_to_renewal(dict(row))
            return None

    @debug
    def get_by_spa_id(self, spa_id: int) -> Optional[PendingRenewal]:
        """Get pending renewal by SPA ID"""
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM certif_pending_renewals WHERE spa_id = ?", (int(spa_id),)
            ).fetchone()
            if row:
                return self._row_to_renewal(dict(row))
            return None

    @debug
    def get_all_by_contact(self, contact_number: str) -> List[PendingRenewal]:
        """Get all pending renewals by contact"""
        std_number = standardize_phone_number(contact_number)
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM certif_pending_renewals 
                WHERE contact_number = ? 
                AND status NOT IN ('customer_retention', 'scheduling_form_sent') 
                ORDER BY created_at ASC
                """,
                (std_number,),
            ).fetchall()
            return [self._row_to_renewal(dict(row)) for row in rows]

    def _row_to_renewal(self, row: Dict[str, Any]) -> PendingRenewal:
        """Convert database row to PendingRenewal object"""
        return PendingRenewal(
            company_name=row["company_name"],
            document=row["document"],
            contact_number=row["contact_number"],
            contact_name=row["contact_name"],
            deal_type=row["deal_type"],
            spa_id=row["spa_id"],
            status=row["status"],
            created_at=row.get("created_at"),
            last_interaction=row.get("last_interaction"),
            is_processing=bool(row.get("is_processing", 0)),
        )


class SQLiteSessionRepository(ISessionRepository):
    """SQLite implementation of session repository"""

    @debug
    def create_session(self, session: ContactSession) -> ContactSession:
        """Create new session"""
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO contact_sessions 
                (contact_number, expected_commands, received_commands, status, created_at) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.contact_number,
                    session.expected_commands,
                    session.received_commands,
                    session.status,
                    session.created_at,
                ),
            )
            conn.commit()
            session.session_id = cur.lastrowid
            return session

    @debug
    def get_active_session(self, contact_number: str) -> Optional[ContactSession]:
        """Get active session"""
        std_number = standardize_phone_number(contact_number)
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM contact_sessions 
                WHERE contact_number = ? AND status = 'active'
                """,
                (std_number,),
            ).fetchone()
            if row:
                return self._row_to_session(dict(row))
            return None

    @debug
    def update_session(self, session: ContactSession) -> bool:
        """Update session"""
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                UPDATE contact_sessions 
                SET received_commands = ?, status = ?
                WHERE id = ?
                """,
                (session.received_commands, session.status, session.session_id),
            )
            conn.commit()
            return cur.rowcount > 0

    @debug
    def get_expired_sessions(self, timeout_minutes: int) -> List[ContactSession]:
        """Get expired sessions"""
        cutoff = datetime.now() - timedelta(minutes=timeout_minutes)
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM contact_sessions
                WHERE status = 'active' AND created_at <= ?
                """,
                (cutoff,),
            ).fetchall()
            return [self._row_to_session(dict(row)) for row in rows]

    def _row_to_session(self, row: Dict[str, Any]) -> ContactSession:
        """Convert database row to ContactSession object"""
        return ContactSession(
            contact_number=row["contact_number"],
            expected_commands=row["expected_commands"],
            received_commands=row["received_commands"],
            status=row["status"],
            created_at=row.get("created_at"),
            session_id=row.get("id"),
        )


# Service Classes
class PendingRenewalService:
    """Service for managing pending renewals"""

    def __init__(self, repository: IPendingRenewalRepository):
        self._repository = repository

    @debug
    def add_pending(
        self,
        company_name: str,
        document: str,
        contact_number: str,
        contact_name: str,
        deal_type: str,
        spa_id: int,
        status: str,
    ) -> str:
        """Add pending renewal"""
        renewal = PendingRenewal(
            company_name=company_name,
            document=document,
            contact_number=contact_number,
            contact_name=contact_name,
            deal_type=deal_type,
            spa_id=spa_id,
            status=status,
        )
        return self._repository.add(renewal)

    @debug
    def update_pending(self, spa_id: int, status: str, **kwargs) -> bool:
        """Update pending renewal"""
        update_data = {"status": status}
        update_data.update(kwargs)
        return self._repository.update(spa_id, **update_data)

    @debug
    def get_pending(
        self,
        contact_number: str = None,
        spa_id: int = None,
        context_aware: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get pending renewal"""
        if not any([contact_number, spa_id]):
            raise ValueError("Required contact_number or spa_id")

        if spa_id:
            renewal = self._repository.get_by_spa_id(spa_id)
        else:
            renewal = self._repository.get_by_contact(contact_number, context_aware)

        return renewal.to_dict() if renewal else None


class SessionManager:
    """Service for managing contact sessions"""

    def __init__(
        self,
        session_repository: ISessionRepository,
        renewal_repository: IPendingRenewalRepository,
        timeout_minutes: int = 30,
    ):
        self._session_repository = session_repository
        self._renewal_repository = renewal_repository
        self._timeout_minutes = timeout_minutes

    @debug
    def get_or_create_session(self, contact_number: str) -> Dict[str, Any]:
        """Get or create session for contact"""
        std_number = standardize_phone_number(contact_number)

        # Try to get existing session
        session = self._session_repository.get_active_session(std_number)
        if session:
            return session.__dict__

        # Create new session
        expected_commands = self._count_pending_renewals(std_number)
        session = ContactSession(
            contact_number=std_number, expected_commands=expected_commands
        )

        created_session = self._session_repository.create_session(session)
        return created_session.__dict__

    @debug
    def record_command(self, contact_number: str) -> bool:
        """Record a renewal command"""
        std_number = standardize_phone_number(contact_number)
        session = self._session_repository.get_active_session(std_number)

        if session:
            session.received_commands += 1
            return self._session_repository.update_session(session)

        return False

    @debug
    def check_expired_sessions(self) -> List[Dict[str, Any]]:
        """Check for expired sessions"""
        expired_sessions = self._session_repository.get_expired_sessions(
            self._timeout_minutes
        )
        return [session.__dict__ for session in expired_sessions]

    @debug
    def finalize_session(self, contact_number: str) -> bool:
        """Finalize session if conditions are met"""
        from app.services.digisac.digisac_services import close_ticket_digisac

        std_number = standardize_phone_number(contact_number)
        session = self._session_repository.get_active_session(std_number)

        if not session:
            return False

        # Check if session should be finalized
        should_finalize = session.is_complete() or session.is_expired(
            self._timeout_minutes
        )

        if should_finalize:
            # Close ticket
            close_ticket_digisac(std_number)

            # Update session status
            session.status = "completed"
            success = self._session_repository.update_session(session)

            if success:
                logger.info(f"Session finalized for {contact_number}")

            return success

        return False

    def _count_pending_renewals(self, contact_number: str) -> int:
        """Count pending renewals for contact"""
        renewals = self._renewal_repository.get_all_by_contact(contact_number)
        return len([r for r in renewals if r.status == "pending"])


# Legacy function wrappers for backward compatibility
def add_pending(*args, **kwargs):
    """Legacy wrapper for add_pending"""
    repository = SQLitePendingRenewalRepository()
    service = PendingRenewalService(repository)
    return service.add_pending(*args, **kwargs)


def update_pending(*args, **kwargs):
    """Legacy wrapper for update_pending"""
    repository = SQLitePendingRenewalRepository()
    service = PendingRenewalService(repository)
    return service.update_pending(*args, **kwargs)


def get_pending(*args, **kwargs):
    """Legacy wrapper for get_pending"""
    repository = SQLitePendingRenewalRepository()
    service = PendingRenewalService(repository)
    return service.get_pending(*args, **kwargs)


# Factory functions
def create_pending_renewal_service() -> PendingRenewalService:
    """Factory for creating pending renewal service"""
    repository = SQLitePendingRenewalRepository()
    return PendingRenewalService(repository)


def create_session_manager() -> SessionManager:
    """Factory for creating session manager"""
    session_repo = SQLiteSessionRepository()
    renewal_repo = SQLitePendingRenewalRepository()
    return SessionManager(session_repo, renewal_repo)
