# app/core/lifecycle.py
"""
Application lifecycle management following SOLID principles.
"""

import signal
import sys
import atexit
from typing import List, Optional
from threading import Thread
import time

from .interfaces import IWorker, ILogger, IService
from .container import container


class ApplicationLifecycle:
    """
    Manages application startup, running, and shutdown phases.
    Follows Single Responsibility Principle.
    """

    def __init__(self):
        self._workers: List[IWorker] = []
        self._services: List[IService] = []
        self._threads: List[Thread] = []
        self._logger: Optional[ILogger] = None
        self._shutdown_requested = False

    def register_worker(self, worker: IWorker) -> "ApplicationLifecycle":
        """Register a background worker"""
        self._workers.append(worker)
        return self

    def register_service(self, service: IService) -> "ApplicationLifecycle":
        """Register a service"""
        self._services.append(service)
        return self

    def initialize(self) -> None:
        """Initialize all services and setup signal handlers"""
        self._logger = container.try_resolve(ILogger)

        # Initialize all services
        for service in self._services:
            try:
                service.initialize()
                if self._logger:
                    self._logger.info(
                        f"✅ Service {service.__class__.__name__} initialized"
                    )
            except Exception as e:
                if self._logger:
                    self._logger.error(
                        f"❌ Failed to initialize {service.__class__.__name__}: {e}"
                    )
                raise

        # Setup signal handlers
        self._setup_signal_handlers()

        if self._logger:
            self._logger.info("🚀 Application lifecycle initialized")

    def start_workers(self) -> None:
        """Start all registered workers in separate threads"""
        for worker in self._workers:
            thread = Thread(
                target=self._run_worker_safe,
                args=(worker,),
                daemon=True,
                name=worker.__class__.__name__,
            )
            thread.start()
            self._threads.append(thread)

            if self._logger:
                self._logger.info(f"🧵 Worker {worker.__class__.__name__} started")

    def run_monitoring_loop(self) -> None:
        """Run main monitoring loop"""
        if self._logger:
            self._logger.info("🔄 Starting monitoring loop")

        while not self._shutdown_requested:
            try:
                # Check worker health
                for worker in self._workers:
                    if not worker.is_healthy():
                        if self._logger:
                            self._logger.warning(
                                f"⚠️ Worker {worker.__class__.__name__} is unhealthy"
                            )

                # Check thread health
                for thread in self._threads:
                    if not thread.is_alive():
                        if self._logger:
                            self._logger.error(
                                f"❌ Thread {thread.name} died unexpectedly"
                            )
                        raise RuntimeError(f"Critical thread {thread.name} stopped")

                time.sleep(5)

            except KeyboardInterrupt:
                self._shutdown_requested = True
            except Exception as e:
                if self._logger:
                    self._logger.error(f"💥 Monitoring loop error: {e}")
                raise

    def shutdown(self) -> None:
        """Graceful shutdown of all components"""
        if self._logger:
            self._logger.info("🛑 Starting graceful shutdown...")

        self._shutdown_requested = True

        # Stop workers
        for worker in self._workers:
            try:
                worker.stop()
                if self._logger:
                    self._logger.info(f"✅ Worker {worker.__class__.__name__} stopped")
            except Exception as e:
                if self._logger:
                    self._logger.error(
                        f"❌ Error stopping worker {worker.__class__.__name__}: {e}"
                    )

        # Cleanup services
        for service in self._services:
            try:
                service.cleanup()
                if self._logger:
                    self._logger.info(
                        f"✅ Service {service.__class__.__name__} cleaned up"
                    )
            except Exception as e:
                if self._logger:
                    self._logger.error(
                        f"❌ Error cleaning up service {service.__class__.__name__}: {e}"
                    )

        if self._logger:
            self._logger.info("👋 Application shutdown complete")

        sys.exit(0)

    def _run_worker_safe(self, worker: IWorker) -> None:
        """Safely run a worker with error handling"""
        try:
            worker.start()
        except Exception as e:
            if self._logger:
                self._logger.error(
                    f"💥 Worker {worker.__class__.__name__} crashed: {e}"
                )
            raise

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""

        def signal_handler(signum, frame):
            if self._logger:
                self._logger.info(
                    f"📡 Received signal {signum}, initiating shutdown..."
                )
            self.shutdown()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(self.shutdown)
