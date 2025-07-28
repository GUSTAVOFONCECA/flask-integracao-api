# app/run.py

"""
Main entry point for the aplicação.
Este script inicializa a aplicação Flask, configura o logging, dispara o LocalTunnel
e trata encerramentos de forma graciosa.
"""

import sys
import signal
import atexit
from threading import Thread
import time
from waitress import serve
from app import create_app
from app.database.database import init_db
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
        self.worker_threads = []  # Lista de armazenamento das threads dos workers

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

    def start_workers(self):
        """Inicia todos os workers da aplicação em threads separadas"""
        workers = [self.start_ticket_flow_worker, self.start_session_worker]

        for worker in workers:
            thread = Thread(target=worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)
            self.flask_app.logger.info(f"🧵 Thread do {worker.__name__} iniciada")

    def start_ticket_flow_worker(self):
        """Inicia o worker de fluxo de tickets com contexto (app)"""
        with self.flask_app.app_context():
            from app.workers.ticket_flow_worker import run_ticket_flow_worker

            run_ticket_flow_worker()

    def start_session_worker(self):
        """Inicia o worker de sessões com contexto (app)"""
        with self.flask_app.app_context():
            from app.workers.session_worker import run_session_worker

            run_session_worker()


def main() -> None:
    """
    Função principal de inicialização da aplicação.

    Fluxo de execução:
    1. Configura logging (arquivo + console).
    2. Define Config.ENV como 'development' para ajustar níveis de log.
    3. Valida variáveis de ambiente obrigatórias.
    4. Testa health check da API.
    5. Inicia Flask em thread.
    6. Dispara LocalTunnel em background.
    7. Loop de monitoramento.
    """
    manager = AppManager()

    try:
        # Configure logging
        configure_logging(manager.flask_app)  # Movido para cá

        app_logger = manager.flask_app.logger

        # Validação agora é feita dentro do configure_logging
        app_logger.info("🛠️ Verificando configurações básicas...")
        app_logger.info("✅ Configurações válidas")

        # Testar health check da API antes de subir o servidor
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

        # Inicia DB antes de tudo
        init_db()
        app_logger.info("Banco de dados inicializado")

        # Inicia todos os workers
        manager.start_workers()

        # Iniciar Flask em thread
        flask_thread = Thread(target=manager.run_flask_server, daemon=True)
        flask_thread.start()
        manager.worker_threads.append(flask_thread)

        # Disparar o LocalTunnel em background
        start_localtunnel()
        app_logger.info("✅ Túnel iniciado (monitoramento automático ativado)")

        # Loop de monitoramento
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
