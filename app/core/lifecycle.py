# app/core/lifecycle.py
"""
Application lifecycle management following SOLID principles.
"""

import logging
import signal
import threading
from typing import List
from concurrent.futures import ThreadPoolExecutor

from app.core.interfaces import IService, IWorker, IHealthChecker

logger = logging.getLogger(__name__)


class ApplicationLifecycle:
    """
    Application lifecycle manager following Single Responsibility Principle.
    Manages startup, shutdown, and monitoring of application components.
    """

    def __init__(self):
        self.services: List[IService] = []
        self.workers: List[IWorker] = []
        self.health_checker: IHealthChecker = None
        self.is_running = False
        self.shutdown_event = threading.Event()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def register_service(self, service: IService) -> None:
        """Register a service for lifecycle management"""
        self.services.append(service)
        logger.debug(f"Registered service: {service.__class__.__name__}")

    def register_worker(self, worker: IWorker) -> None:
        """Register a worker for lifecycle management"""
        self.workers.append(worker)
        logger.debug(f"Registered worker: {worker.__class__.__name__}")

    def set_health_checker(self, health_checker: IHealthChecker) -> None:
        """Set health checker"""
        self.health_checker = health_checker

    def initialize(self) -> None:
        """Initialize all registered components"""
        logger.info("🔄 Initializing application components...")

        # Initialize services
        for service in self.services:
            try:
                if hasattr(service, "initialize"):
                    service.initialize()
                logger.debug(f"✅ Initialized service: {service.__class__.__name__}")
            except Exception as e:
                logger.error(
                    f"❌ Failed to initialize service {service.__class__.__name__}: {e}"
                )
                raise

        logger.info("✅ All components initialized successfully")

    def start_workers(self) -> None:
        """Start all registered workers"""
        logger.info("🚀 Starting background workers...")

        for worker in self.workers:
            try:
                worker.start()
                logger.debug(f"✅ Started worker: {worker.__class__.__name__}")
            except Exception as e:
                logger.error(
                    f"❌ Failed to start worker {worker.__class__.__name__}: {e}"
                )
                # Continue with other workers

        logger.info("✅ All workers started successfully")

    def run_monitoring_loop(self) -> None:
        """Run main monitoring loop"""
        self.is_running = True
        logger.info("🔍 Starting monitoring loop...")

        try:
            while not self.shutdown_event.is_set():
                self._perform_health_checks()

                # Wait for 30 seconds or shutdown signal
                if self.shutdown_event.wait(timeout=30):
                    break

        except KeyboardInterrupt:
            logger.info("🛑 Received shutdown signal")
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Graceful shutdown of all components"""
        if not self.is_running:
            return

        logger.info("🛑 Initiating graceful shutdown...")
        self.is_running = False
        self.shutdown_event.set()

        # Stop workers first
        self._stop_workers()

        # Cleanup services
        self._cleanup_services()

        logger.info("✅ Graceful shutdown completed")

    def _perform_health_checks(self) -> None:
        """Perform health checks on components"""
        if not self.health_checker:
            return

        try:
            health_status = self.health_checker.check_health()
            if not health_status.get("healthy", False):
                logger.warning(f"⚠️ Health check failed: {health_status}")
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")

    def _stop_workers(self) -> None:
        """Stop all workers"""
        logger.info("🛑 Stopping workers...")

        with ThreadPoolExecutor(max_workers=len(self.workers)) as executor:
            futures = []

            for worker in self.workers:
                future = executor.submit(self._stop_worker_safely, worker)
                futures.append(future)

            # Wait for all workers to stop
            for future in futures:
                try:
                    future.result(timeout=10)
                except Exception as e:
                    logger.error(f"❌ Error stopping worker: {e}")

    def _stop_worker_safely(self, worker: IWorker) -> None:
        """Safely stop a worker"""
        try:
            worker.stop()
            logger.debug(f"✅ Stopped worker: {worker.__class__.__name__}")
        except Exception as e:
            logger.error(f"❌ Error stopping worker {worker.__class__.__name__}: {e}")

    def _cleanup_services(self) -> None:
        """Cleanup all services"""
        logger.info("🧹 Cleaning up services...")

        for service in reversed(self.services):  # Reverse order for cleanup
            try:
                if hasattr(service, "cleanup"):
                    service.cleanup()
                logger.debug(f"✅ Cleaned up service: {service.__class__.__name__}")
            except Exception as e:
                logger.error(
                    f"❌ Error cleaning up service {service.__class__.__name__}: {e}"
                )

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"🔔 Received signal {signum}")
        self.shutdown_event.set()
