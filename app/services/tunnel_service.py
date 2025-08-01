# app/services/tunnel_service.py
"""
Tunnel service implementation following SOLID principles.
"""

import logging
import subprocess
import time
import requests
from typing import Optional

from app.core.interfaces import ITunnelService, IConfigProvider

logger = logging.getLogger(__name__)


class TunnelService(ITunnelService):
    """
    Tunnel service implementation following Single Responsibility Principle.
    Only responsible for managing tunnel connections.
    """

    def __init__(self, config: IConfigProvider):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.is_running = False

    def start(self) -> None:
        """Start tunnel service"""
        if self.is_running:
            logger.warning("Tunnel service is already running")
            return

        try:
            port = self.config.get("TUNNEL_PORT", 5478)

            # Start localtunnel process
            self.process = subprocess.Popen(
                ["npx", "localtunnel", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait for tunnel to be ready and extract URL
            self._wait_for_tunnel_ready()
            self.is_running = True

            logger.info(f"✅ Tunnel started successfully: {self.public_url}")

        except Exception as e:
            logger.error(f"❌ Failed to start tunnel: {e}")
            self.cleanup()
            raise

    def stop(self) -> None:
        """Stop tunnel service"""
        if not self.is_running:
            return

        self.cleanup()
        logger.info("🛑 Tunnel service stopped")

    def get_public_url(self) -> str:
        """Get public URL"""
        return self.public_url or ""

    def _wait_for_tunnel_ready(self, timeout: int = 30) -> None:
        """Wait for tunnel to be ready and extract public URL"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.process and self.process.poll() is not None:
                # Process has terminated
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"Tunnel process terminated: {stderr}")

            # Try to read stdout for URL
            if self.process and self.process.stdout:
                try:
                    line = self.process.stdout.readline()
                    if line and "your url is:" in line.lower():
                        self.public_url = line.split(":")[-1].strip()
                        # Update config with public URL
                        self.config.TUNNEL_PUBLIC_IP = self.public_url
                        return
                except Exception:
                    pass

            time.sleep(1)

        raise TimeoutError("Timeout waiting for tunnel to be ready")

    def cleanup(self) -> None:
        """Cleanup tunnel resources"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.warning(f"Error during tunnel cleanup: {e}")
            finally:
                self.process = None

        self.is_running = False
        self.public_url = None

    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()


# Legacy function for backward compatibility
def start_localtunnel(config: IConfigProvider) -> TunnelService:
    """Start tunnel service - legacy wrapper"""
    tunnel_service = TunnelService(config)
    tunnel_service.start()
    return tunnel_service
