"""
Main entry point for the application
    This script initializes the Flask application, sets up the localtunnel,
    and handles graceful shutdowns. It also includes a pre-initialization check
"""

# app/run.py
import sys
import signal
import atexit
import threading
import time
from waitress import serve
from app import create_app
from app.services.tunnel_service import start_localtunnel
from app.config import Config


class AppManager:
    def __init__(self):
        self.tunnel: dict[str, any] = None  # type: ignore
        self.flask_app = create_app()

    def run_flask_server(self):
        """Inicia o servidor Flask/Waitress"""
        if Config.ENV == "production":
            self.flask_app.logger.info("\nℹ️ Iniciando servidor em modo produção\n")
            serve(self.flask_app, host="0.0.0.0", port=Config.TUNNEL_PORT)
        else:
            self.flask_app.logger.info(
                "\nℹ️ Iniciando servidor em modo desenvolvimento\n"
            )
            self.flask_app.run(
                host="0.0.0.0", port=Config.TUNNEL_PORT, debug=True, use_reloader=False
            )

    def graceful_shutdown(self):
        """Encerramento seguro"""
        self.flask_app.logger.info("\nℹ️ Encerrando aplicação...\n")
        if self.tunnel and self.tunnel["process"]:
            self.tunnel["process"].terminate()
        sys.exit(0)


def main():
    try:
        # Adicione verificação pré-inicialização
        print("🛠️  Verificando configurações básicas...")
        Config.validate()
        print("✅ Configurações válidas")

        # Forçar modo desenvolvimento para testes
        Config.ENV = "development"
        flask_app = create_app()

        # Teste mínimo do Flask
        print("🔥 Testando rota básica...")
        with flask_app.test_client() as client:
            response = client.get("/api/data")
            assert (
                response.status_code == 200
            ), f"Erro na rota básica: {response.status_code}"
        print("✅ Rotas básicas funcionando")

    except (AssertionError, ValueError, RuntimeError) as e:
        print(f"❌ Falha crítica durante pré-teste: {str(e)}")
        sys.exit(1)

    manager = AppManager()
    atexit.register(manager.graceful_shutdown)
    signal.signal(signal.SIGINT, lambda s, f: manager.graceful_shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: manager.graceful_shutdown())

    try:
        # Iniciar Flask em thread
        flask_thread = threading.Thread(target=manager.run_flask_server, daemon=True)
        flask_thread.start()

        # Iniciar túnel após o flask
        manager.tunnel = start_localtunnel()

        # Monitorar status
        while True:
            if not flask_thread.is_alive():
                raise RuntimeError("\n🔻 Servidor Flask parou inesperadamente\n")

            if manager.tunnel["process"].poll() is not None:
                raise RuntimeError("\n🔻 Túnel encerrado inesperadamente\n")

            time.sleep(5)

    except (RuntimeError, ConnectionError) as e:
        manager.flask_app.logger.critical("\n❌ Falha crítica:\n%s\n", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
