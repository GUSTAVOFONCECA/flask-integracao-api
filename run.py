# run.py
import sys
import signal
import atexit
import threading
import time
from app import create_app
from app.services.tunnel_service import start_localtunnel
from app.config import Config


class AppManager:
    def __init__(self):
        self.tunnel = None
        self.flask_app = create_app()

    def run_flask_server(self):
        """Inicia o servidor Flask/Waitress"""
        if Config.ENV == "production":
            from waitress import serve

            self.flask_app.logger.info("\nℹ️ Iniciando servidor em modo produção\n")
            serve(self.flask_app, host="0.0.0.0", port=Config.TUNNEL_PORT)
        else:
            self.flask_app.logger.info("\nℹ️ Iniciando servidor em modo desenvolvimento\n")
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

    except Exception as e:
        manager.flask_app.logger.critical(f"\n❌ Falha crítica:\n{str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
