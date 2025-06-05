# app/services/tunnel_service.py

"""
Serviço para gerenciar a inicialização e reinicialização do túnel LocalTunnel
com subdomínio fixo (logic-1997) e porta configurada em Config.TUNNEL_PORT.

1. Injeta %APPDATA%\npm no PATH para que o Windows consiga encontrar lt.cmd.
2. Invoca 'lt' como string única via shell=True, pois o npm cria um arquivo lt.cmd.
3. Monitora o stdout do processo: se receber "your url is: ..." SEM o subdomínio correto,
   encerra o processo e tenta novamente até que "logic-1997" esteja alocado.
4. Obtém e armazena o IP público para uso no aviso do LocalTunnel.
"""

import os
import time
import logging
import subprocess
import threading
import requests
from typing import Optional, Dict, Any
from app.config import Config

logger = logging.getLogger(__name__)

# Subdomínio desejado
TUNNEL_SUBDOMAIN = "logic-1997"
# Tempo (em segundos) entre tentativas de reiniciar o tunnel após falha
TUNNEL_RETRY_INTERVAL = 5
# Intervalo (em segundos) para checar se o processo ainda está vivo
TUNNEL_CHECK_INTERVAL = 10
# Armazenamento global do IP público
tunnel_public_ip = None


def get_public_ip() -> Optional[str]:
    """Obtém o IP público do computador usando a API ipify."""
    global tunnel_public_ip

    if tunnel_public_ip:
        return tunnel_public_ip

    try:
        logger.info("🔄 Obtendo IP público...")
        response = requests.get("https://api.ipify.org?format=json", timeout=5)
        if response.status_code == 200:
            tunnel_public_ip = response.json().get("ip")
            Config.TUNNEL_PUBLIC_IP = tunnel_public_ip
            logger.info(f"🌐 IP Público obtido: {tunnel_public_ip}")
            return tunnel_public_ip
    except Exception as e:
        logger.error(f"❌ Falha ao obter IP público: {str(e)}")

    return None


def _monitor_output(stream, url_event, url_container, subdomain, process):
    """
    Monitora o stdout/stderr do processo 'lt' linha a linha.
    - Assim que encontrar "your url is: XXX", verifica se XXX contém o subdomínio correto.
      * Se contiver, seta url_event e grava a URL em url_container[0].
      * Se NÃO contiver, encerra o processo imediatamente (força nova tentativa).
    """
    while True:
        raw_line = stream.readline()
        if not raw_line:
            break

        # Se a linha não terminou em '\n', aguarda um pouco até vir completa
        if not raw_line.endswith(b"\n"):
            time.sleep(0.1)
            continue

        try:
            line = raw_line.decode("utf-8", errors="replace").strip()
        except UnicodeDecodeError:
            line = raw_line.decode("latin-1", errors="replace").strip()

        # Se o processo já morreu, não faz mais nada
        if process.poll() is not None:
            return

        # Quando o lt imprime "your url is: https://XXXXXXXX.loca.lt"
        if "your url is:" in line:
            url_candidate = line.split("your url is:")[1].strip()
            # Se o link contiver o subdomínio exato, sucesso
            if subdomain in url_candidate:
                logger.info("LT retornou URL correta: %s", url_candidate)
                url_container[0] = url_candidate
                url_event.set()
                return
            else:
                # Subdomínio diferente: mata o processo e retorna (forçando nova tentativa)
                logger.warning(
                    "LT retornou subdomínio incorreto (%s). Finalizando processo para retry.",
                    url_candidate,
                )
                try:
                    process.terminate()
                except OSError:
                    pass
                return

        # (Opcional) Log de DEBUG para ver tudo o que o lt está emitindo
        logger.debug("LT Output: %s", line)


def _start_tunnel_process(cmd_str: str) -> subprocess.Popen:
    """
    Inicia o localtunnel via subprocess, em modo shell (necessário no Windows
    para que ele resolva o arquivo lt.cmd gerado pelo npm).
    """
    return subprocess.Popen(
        cmd_str,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,  # essencial no Windows para chamar lt.cmd
    )


def _try_start_tunnel() -> Optional[Dict[str, Any]]:
    """
    Tenta iniciar o localtunnel até 3 vezes em sequência, retornando um dict
    com {'process': Popen, 'url': str} se der certo. Caso contrário, retorna None.
    A cada tentativa, monitora o stdout: se vier subdomínio incorreto, mata o processo
    imediatamente para tentar de novo, sem esperar timeout.
    """
    max_attempts = 3
    subdomain = TUNNEL_SUBDOMAIN

    for attempt in range(1, max_attempts + 1):
        process = None
        try:
            logger.info("🚀 Tentativa %d/%d de iniciar o túnel", attempt, max_attempts)

            # 1) Injetar no PATH a pasta global do npm (onde está lt.cmd), para que
            #    o Windows consiga “achar” o comando.
            npm_global = os.path.expandvars(r"%APPDATA%\npm")
            os.environ["PATH"] = npm_global + os.pathsep + os.environ.get("PATH", "")

            # 2) Monta o comando como string. Note que usamos Config.TUNNEL_PORT.
            cmd = (
                f"lt --port {Config.TUNNEL_PORT} "
                f"--subdomain {subdomain} "
                f"--local-host 0.0.0.0 "
                f"--print-requests"
            )

            # 3) Inicia o processo com shell=True
            process = _start_tunnel_process(cmd)

            # 4) Prepara evento e container para receber a URL
            url_event = threading.Event()
            url_container = [None]

            # 5) Inicia threads que monitoram stdout e stderr
            threading.Thread(
                target=_monitor_output,
                args=(process.stdout, url_event, url_container, subdomain, process),
                daemon=True,
            ).start()
            threading.Thread(
                target=_monitor_output,
                args=(process.stderr, url_event, url_container, subdomain, process),
                daemon=True,
            ).start()

            # 6) Aguarda até 60s pela URL correta. Se não vier, cai no except e encerra processo.
            if url_event.wait(timeout=60):
                url = url_container[0]
                # Garante de novo que o subdomínio está correto
                if isinstance(url, str) and subdomain in str(url):
                    return {"process": process, "url": url}
                else:
                    raise RuntimeError(f"URL inválida ou subdomínio incorreto: {url}")

            # Se timeout sem receber url_event.set(), lança erro para reiniciar
            raise RuntimeError("Timeout aguardando URL do localtunnel")

        except (
            subprocess.SubprocessError,
            RuntimeError,
            UnicodeDecodeError,
            OSError,
        ) as e:
            logger.warning("Falha na tentativa %d: %s", attempt, e)
            # Se o processo ainda estiver vivo, encerra para liberar recursos
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait()
                except OSError:
                    pass
            # Espera antes de tentar de novo (2^attempt segundos: 2, 4, 8)
            time.sleep(2**attempt)

    # Se fez 3 tentativas e não conseguiu, retorna None
    return None


def _run_tunnel_loop():
    """
    Loop infinito que tenta manter o túnel ativo.
    - Chama _try_start_tunnel() até ele retornar um dict válido.
    - Se o processo LT morrer por algum motivo, reinicia.
    - Se retornar None (3 tentativas falhas), aguarda TUNNEL_RETRY_INTERVAL e tenta de novo.
    """
    global tunnel_public_ip

    # Obter IP público apenas uma vez no início
    get_public_ip()

    while True:
        result = _try_start_tunnel()
        if result is not None:
            process = result["process"]
            url = result["url"]
            logger.info("🌐 Túnel ativo em: %s", url)

            # Enquanto o processo estiver executando, apenas dorme.
            while process.poll() is None:
                time.sleep(TUNNEL_CHECK_INTERVAL)

            logger.warning("Túnel encerrado inesperadamente. Reiniciando...")

        else:
            logger.error(
                "Não foi possível alocar subdomínio '%s'. "
                "Tentando novamente em %ds...",
                TUNNEL_SUBDOMAIN,
                TUNNEL_RETRY_INTERVAL,
            )
        time.sleep(TUNNEL_RETRY_INTERVAL)


def start_localtunnel():
    """
    Dispara a thread daemon que mantém o túnel ativo: toda vez que o lt retornar
    subdomínio errado ou morrer, ele reinicia automaticamente.
    """
    # Obter IP público antes de iniciar o túnel
    public_ip = get_public_ip()
    if public_ip:
        logger.info(f"🌐 IP Público do túnel: {public_ip}")
        Config.TUNNEL_PUBLIC_IP = public_ip

    tunnel_thread = threading.Thread(target=_run_tunnel_loop, daemon=True)
    tunnel_thread.start()
