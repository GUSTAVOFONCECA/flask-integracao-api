# app/run.py

"""
Main entry point for the aplicação.
Este script inicializa a aplicação Flask, configura o logging, dispara o LocalTunnel
e trata encerramentos de forma graciosa.
"""

import sys
import signal
import atexit
import threading
import time

from waitress import serve
from app import create_app
from app.services.tunnel_service import start_localtunnel
from app.config import Config, configure_logging


class AppManager:
    """
    Gerenciador principal da aplicação Flask e serviços associados.

    :ivar flask_app: Instância da aplicação Flask
    :vartype flask_app: flask.Flask
    """

    def __init__(self):
        self.flask_app = create_app()

    def run_flask_server(self):
        """
        Inicia o servidor Flask/Waitress conforme o ambiente configurado.

        - Em 'production' usa Waitress.
        - Em 'development' usa o servidor embutido do Flask.
        """
        if Config.ENV == "production":
            self.flask_app.logger.info("Iniciando servidor em modo produção")
            serve(self.flask_app, host="0.0.0.0", port=Config.TUNNEL_PORT)
        else:
            self.flask_app.logger.info("Iniciando servidor em modo desenvolvimento")
            self.flask_app.run(
                host="0.0.0.0",
                port=Config.TUNNEL_PORT,
                debug=True,
                use_reloader=False,
            )

    def graceful_shutdown(self):
        """
        Executa o desligamento seguro da aplicação:
        1. Loga mensagem de encerramento.
        2. Sai do processo com código 0.
        """
        self.flask_app.logger.info("Encerrando aplicação...")
        sys.exit(0)


def main() -> None:
    """
    Função principal de inicialização da aplicação.

    Fluxo de execução:
    1. Valida variáveis de ambiente obrigatórias.
    2. Define Config.ENV como 'development' para ajustar níveis de log.
    3. Configura logging (arquivo + console).
    4. Testa health check da API.
    5. Inicia Flask em thread.
    6. Dispara LocalTunnel em background.
    7. Loop de monitoramento.
    """
    manager = AppManager()

    try:
        # Configure logging FIRST
        configure_logging(manager.flask_app)  # Movido para cá

        app_logger = manager.flask_app.logger

        # Validação agora é feita dentro do configure_logging
        app_logger.info("🛠️ Verificando configurações básicas...")
        app_logger.info("✅ Configurações válidas")

        # 4) Testar health check da API antes de subir o servidor
        app_logger.info("🔥 Testando health check da API...")
        flask_app = manager.flask_app
        with flask_app.test_client() as client:
            response = client.get(
                "/api/health/",
                headers={"X-API-Key": Config.API_KEY},
            )
            assert (
                response.status_code == 200
            ), f"Status inválido: {response.status_code}"
            data = response.get_json()
            assert data["status"] == "healthy", f"Status inválido: {data.get('status')}"
            assert (
                data["environment"] == Config.ENV
            ), f"Ambiente incorreto: {data.get('environment')}"
        app_logger.info("✅ Testes prévios concluídos")

        # Registra sinais de encerramento gracioso
        atexit.register(manager.graceful_shutdown)
        signal.signal(signal.SIGINT, lambda s, f: manager.graceful_shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: manager.graceful_shutdown())

        # 5) Iniciar Flask em thread
        flask_thread = threading.Thread(target=manager.run_flask_server, daemon=True)
        flask_thread.start()

        # 6) Disparar o LocalTunnel em background
        start_localtunnel()
        app_logger.info("✅ Túnel iniciado (monitoramento automático ativado)")

        # 7) Loop de monitoramento
        while True:
            if not flask_thread.is_alive():
                raise RuntimeError("Servidor Flask parou inesperadamente")
            time.sleep(5)

    except (RuntimeError, ConnectionError, AssertionError, EnvironmentError) as e:
        # Se manager.flask_app existir, usamos o logger; caso contrário, printar
        if manager and manager.flask_app:
            manager.flask_app.logger.critical("\nFalha crítica:\n%s\n", str(e))
        else:
            app_logger.critical(f"\nFalha crítica:\n{str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
