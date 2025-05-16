# app/services/tunnel_service.py
import sys
import time
import logging
import subprocess
import threading
from app.config import Config

logger = logging.getLogger(__name__)


def start_localtunnel():
    """Inicia o túnel com 3 tentativas e verificação de subdomínio"""
    max_attempts = 3
    subdomain = "logic-1997"

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"\n🚀 Tentativa {attempt}/{max_attempts} de iniciar o túnel\n")

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

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                shell=True,
            )

            url_event = threading.Event()
            url = None

            def monitor_output(stream, is_error=False):
                nonlocal url
                while True:
                    raw_line = stream.readline()
                    if not raw_line.endswith(b'\n'):
                        time.sleep(0.1)  # Pequeno delay para buffers incompletos
                        continue

                    try:
                        # Remova o .encode() e decodifique corretamente
                        line = raw_line.decode("utf-8", errors="replace").strip()
                    except UnicodeDecodeError:
                        line = raw_line.decode("latin-1", errors="replace").strip()

                    if is_error:
                        logger.error(f"\n❌ LT Error: {line}\n")
                    else:
                        logger.debug(f"\nℹ️ LT Output: {line}\n")

                    if "your url is:" in line:
                        url_candidate = line.split("your url is:")[1].strip()
                        if subdomain in url_candidate:
                            url = url_candidate
                            url_event.set()
                        else:
                            logger.warning(
                                f"\n⚠️ Subdomínio incorreto: {url_candidate}\n"
                            )
                            process.terminate()

            stdout_thread = threading.Thread(
                target=monitor_output, args=(process.stdout, False), daemon=True
            )
            stderr_thread = threading.Thread(
                target=monitor_output, args=(process.stderr, True), daemon=True
            )

            stdout_thread.start()
            stderr_thread.start()

            if url_event.wait(timeout=60):
                if url and subdomain in url:
                    logger.info(f"\n✅ Túnel estabelecido: {url}\n")
                    return {"process": process, "url": url}
                else:
                    logger.warning(f"\n⚠️ Subdomínio não encontrado na URL\n")
                    raise RuntimeError("Subdomínio inválido")

            logger.warning("\n⚠️ Timeout atingido\n")
            raise RuntimeError("Timeout na obtenção da URL")

        except RuntimeError as e:
            logger.warning(f"\n⚠️ Falha na tentativa {attempt}:\n{str(e)}\n")
            if process.poll() is None:
                process.terminate()
                process.wait()
            if attempt == max_attempts:
                logger.critical("\n❌ Todas as tentativas falharam\n")
                sys.exit(1)
            time.sleep(2**attempt)  # Backoff exponencial
            continue

        except Exception as e:
            logger.critical(f"\n❌ Erro inesperado:\n{str(e)}", exc_info=True)
            sys.exit(1)

    sys.exit(1)
