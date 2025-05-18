"""
Service for managing localtunnel subprocess and URL acquisition.
"""
# app/services/tunnel_service.py

import sys
import time
import logging
import subprocess
import threading
from app.config import Config

logger = logging.getLogger(__name__)


def _monitor_output(stream, url_event, url_container, subdomain, is_error=False):
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


def _start_tunnel_process(command):
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        shell=True,
    )


def start_localtunnel():
    """Inicia o túnel com 3 tentativas e verificação de subdomínio"""
    max_attempts = 3
    subdomain = "logic-1997"

    for attempt in range(1, max_attempts + 1):
        process = None
        try:
            logger.info(
                "\n🚀 Tentativa %d/%d de iniciar o túnel\n", attempt, max_attempts
            )

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
            url_container = [None]  # Use a mutable container to share url

            stdout_thread = threading.Thread(
                target=_monitor_output,
                args=(
                    process.stdout,
                    url_event,
                    url_container,
                    subdomain,
                    False,
                ),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_monitor_output,
                args=(
                    process.stderr,
                    url_event,
                    url_container,
                    subdomain,
                    True,
                ),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            if url_event.wait(timeout=60):
                url = url_container[0]
                if isinstance(url, str):
                    if subdomain in str(url):
                        logger.info("\n✅ Túnel estabelecido: %s\n", url)
                        return {"process": process, "url": url}
                    else:
                        logger.warning("\n⚠️ Subdomínio não encontrado na URL\n")
                        raise RuntimeError("Subdomínio inválido")
                else:
                    logger.warning("\n⚠️ URL inválida recebida: %s\n", repr(url))
                    raise RuntimeError("URL inválida recebida")

        except RuntimeError as e:
            logger.warning("\n⚠️ Falha na tentativa %d:\n%s\n", attempt, str(e))
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            if attempt == max_attempts:
                logger.critical("\n❌ Todas as tentativas falharam\n")
                sys.exit(1)
            time.sleep(2**attempt)
            continue

        except (OSError, subprocess.SubprocessError) as e:
            logger.critical("\n❌ Erro inesperado:\n%s", str(e), exc_info=True)
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            sys.exit(1)

    sys.exit(1)
