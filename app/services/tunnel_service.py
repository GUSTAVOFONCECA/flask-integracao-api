"""
Service for managing localtunnel subprocess and automatic URL acquisition.
If the tunnel process dies, it will be restarted automatically.
"""

# app/services/tunnel_service.py


import time
import logging
import subprocess
import threading
from typing import Optional
from app.config import Config

logger = logging.getLogger(__name__)

TUNNEL_SUBDOMAIN = "logic-1997"
TUNNEL_RETRY_INTERVAL = 5  # segundos entre tentativas
TUNNEL_CHECK_INTERVAL = 10  # intervalo para verificar se o túnel ainda está ativo


def _monitor_output(stream, url_event, url_container, subdomain, is_error=False):
    """
    Monitor a given output stream (stdout/stderr) of the tunnel process.

    Args:
        stream: Stream to monitor (stdout or stderr).
        url_event: Event used to signal that the URL has been found.
        url_container: Mutable container to store the URL.
        subdomain: Expected subdomain in the tunnel URL.
        is_error: If True, logs the output as error.
    """
    while True:
        raw_line = stream.readline()
        if not raw_line:
            break
        if not raw_line.endswith(b"\n"):
            time.sleep(0.1)
            continue
        try:
            line = raw_line.decode("utf-8", errors="replace").strip()
        except UnicodeDecodeError:
            line = raw_line.decode("latin-1", errors="replace").strip()

        if is_error:
            logger.error("\n❌ LT Error: %s\n", line)
        else:
            logger.debug("\nℹ️ LT Output: %s\n", line)

        if "your url is:" in line:
            url_candidate = line.split("your url is:")[1].strip()
            if subdomain in url_candidate:
                url_container[0] = url_candidate
                url_event.set()
            else:
                logger.warning("\n⚠️ Subdomínio incorreto: %s\n", url_candidate)


def _start_tunnel_process(command) -> subprocess.Popen:
    """
    Start the localtunnel subprocess.

    Args:
        command: Command list to execute the tunnel.

    Returns:
        subprocess.Popen: The started process.
    """
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,  # Para OS windows
    )


def _run_tunnel_loop():
    """
    Loop infinito para manter o túnel ativo. Reinicia automaticamente se falhar.
    """
    while True:
        result = _try_start_tunnel()
        if result is not None:
            process = result["process"]
            url = result["url"]
            logger.info("🌐 Túnel ativo: %s", url)

            # Monitora o processo
            while process.poll() is None:
                time.sleep(TUNNEL_CHECK_INTERVAL)

            logger.warning("⚠️ Túnel encerrado inesperadamente. Reiniciando...")

        else:
            logger.error(
                "❌ Falha ao iniciar o túnel. Tentando novamente em %ds...",
                TUNNEL_RETRY_INTERVAL,
            )

        time.sleep(TUNNEL_RETRY_INTERVAL)


def _try_start_tunnel() -> Optional[dict]:
    """
    Tenta iniciar o túnel localtunnel até 3 vezes e retorna o processo e URL se bem-sucedido.
    """
    max_attempts = 3
    subdomain = TUNNEL_SUBDOMAIN

    for attempt in range(1, max_attempts + 1):
        process = None
        try:
            logger.info("🚀 Tentativa %d/%d de iniciar o túnel", attempt, max_attempts)

            command = [
                "lt",
                "--port",
                str(Config.TUNNEL_PORT),
                "--subdomain",
                subdomain,
                "--local-host",
                "0.0.0.0",
                "--print-requests",
            ]

            process = _start_tunnel_process(command)

            url_event = threading.Event()
            url_container = [None]

            threading.Thread(
                target=_monitor_output,
                args=(process.stdout, url_event, url_container, subdomain, False),
                daemon=True,
            ).start()
            threading.Thread(
                target=_monitor_output,
                args=(process.stderr, url_event, url_container, subdomain, True),
                daemon=True,
            ).start()

            if url_event.wait(timeout=60):
                url = url_container[0]
                if isinstance(url, str) and subdomain in str(url):
                    return {"process": process, "url": url}
                else:
                    raise RuntimeError("URL inválida ou subdomínio incorreto")

            raise RuntimeError("Timeout esperando URL")

        except (subprocess.SubprocessError, RuntimeError, UnicodeDecodeError, OSError) as e:
            logger.warning("⚠️ Falha na tentativa %d: %s", attempt, str(e))
            if process and process.poll() is None:
                process.terminate()
                process.wait()
            time.sleep(2**attempt)

    return None


def start_localtunnel():
    """
    Inicia a thread que mantém o túnel LocalTunnel sempre ativo.
    """
    tunnel_thread = threading.Thread(target=_run_tunnel_loop, daemon=True)
    tunnel_thread.start()
