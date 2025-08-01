# app/worker/ticket_flow_worker
"""
Ticket Flow Worker following SOLID principles.
Implements Single Responsibility and Dependency Inversion.
"""

import time
import json
import logging
from typing import Protocol, Dict, Any, Callable
from abc import ABC, abstractmethod

from app.core.interfaces import IWorker, ILogger
from app.utils.utils import debug


class ITicketQueueService(Protocol):
    """Interface for ticket queue operations"""

    def get_waiting_tickets(self) -> list:
        """Get waiting tickets from queue"""
        ...

    def start_ticket(self, queue_id: int) -> None:
        """Start processing a ticket"""
        ...

    def update_retry_count(self, queue_id: int) -> None:
        """Update retry count for a ticket"""
        ...


class IRouteHandler(Protocol):
    """Interface for route handlers"""

    def execute(self, args: Dict[str, Any], form: Dict[str, Any]) -> None:
        """Execute the route handler"""
        ...


class TicketFlowWorker(IWorker):
    """
    Worker responsible for processing ticket flow queue.
    Follows Single Responsibility Principle.
    """

    def __init__(
        self,
        queue_service: ITicketQueueService,
        route_registry: Dict[str, IRouteHandler],
        logger: ILogger,
        interval_seconds: int = 60,
    ):
        self._queue_service = queue_service
        self._route_registry = route_registry
        self._logger = logger
        self._interval_seconds = interval_seconds
        self._running = False

    @debug
    def start(self) -> None:
        """Start the ticket flow worker"""
        self._running = True
        self._logger.info(
            f"🔁 Starting ticket flow worker (interval: {self._interval_seconds}s)"
        )

        while self._running:
            try:
                self._process_queue()
            except Exception as e:
                self._logger.error(f"Error in ticket flow worker: {e}")

            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        """Stop the ticket flow worker"""
        self._running = False
        self._logger.info("🛑 Ticket flow worker stopped")

    @debug
    def _process_queue(self) -> None:
        """Process waiting tickets in the queue"""
        waiting_tickets = self._queue_service.get_waiting_tickets()

        for ticket in waiting_tickets:
            try:
                self._process_ticket(ticket)
            except Exception as e:
                queue_id = ticket.get("id")
                self._logger.error(f"Error processing ticket {queue_id}: {e}")
                if queue_id:
                    self._queue_service.update_retry_count(queue_id)

    @debug
    def _process_ticket(self, ticket: Dict[str, Any]) -> None:
        """Process a single ticket"""
        queue_id = ticket["id"]
        func_name = ticket["func_name"]
        args_json = ticket["func_args"]

        handler = self._route_registry.get(func_name)
        if not handler:
            self._logger.error(f"Handler {func_name} not found in registry")
            self._queue_service.update_retry_count(queue_id)
            return

        try:
            params = json.loads(args_json)
            args = params.get("args", {})
            form = params.get("form", {})

            handler.execute(args, form)
            self._queue_service.start_ticket(queue_id)

            self._logger.info(f"Successfully processed ticket {queue_id}")

        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in ticket {queue_id}: {e}")
            self._queue_service.update_retry_count(queue_id)
        except Exception as e:
            self._logger.error(f"Error executing handler for ticket {queue_id}: {e}")
            self._queue_service.update_retry_count(queue_id)


class RouteHandlerAdapter(IRouteHandler):
    """
    Adapter for legacy route handlers.
    Implements Adapter Pattern.
    """

    def __init__(self, handler_func: Callable, app_context):
        self._handler_func = handler_func
        self._app_context = app_context

    def execute(self, args: Dict[str, Any], form: Dict[str, Any]) -> None:
        """Execute the adapted route handler"""
        with self._app_context.test_request_context(
            path="/",
            method="POST",
            query_string=args,
            data=form,
        ):
            self._handler_func()


# Factory function for creating ticket flow worker
def create_ticket_flow_worker(
    queue_service: ITicketQueueService,
    route_registry: Dict[str, IRouteHandler],
    logger: ILogger,
    interval_seconds: int = 60,
) -> TicketFlowWorker:
    """Factory function for creating ticket flow worker"""
    return TicketFlowWorker(queue_service, route_registry, logger, interval_seconds)
