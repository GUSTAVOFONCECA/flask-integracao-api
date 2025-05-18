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
from subprocess import Popen
from waitress import serve
from app import create_app
from app.services.tunnel_service import start_localtunnel
from app.config import Config


class AppManager:
    """Gerenciador principal da aplicação Flask e serviços associados

    :ivar tunnel: Dicionário contendo informações do túnel localtunnel
    :vartype tunnel: dict[str, any]
    :ivar flask_app: Instância da aplicação Flask
    :vartype flask_app: flask.Flask
    """

    def __init__(self):
        self.tunnel: dict[str, Popen] = None  # type: ignore
        self.flask_app = create_app()

    def run_flask_server(self):
        """Inicia o servidor Flask/Waitress conforme o ambiente configurado

        :return: None
        :raises RuntimeError: Se ocorrer falha na inicialização do servidor

        .. note::
            - Modo produção: Usa Waitress com logging detalhado
            - Modo desenvolvimento: Usa servidor embutido do Flask
        """
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
        """Executa o desligamento seguro da aplicação

        :return: None
        :raises SystemExit: Sempre levanta exceção para finalização do processo

        .. rubric:: Ações realizadas
        1. Encerra o processo do túnel localtunnel
        2. Finaliza a aplicação Flask
        3. Encerra o processo com código 0
        """
        self.flask_app.logger.info("\nℹ️ Encerrando aplicação...\n")
        if self.tunnel and self.tunnel["process"]:
            self.tunnel["process"].terminate()
        sys.exit(0)


def main() -> None:
    """Função principal de inicialização da aplicação

    :return: None
    :raises AssertionError: Se teste das rotas básicas falhar
    :raises RuntimeError: Se houver falha no monitoramento de componentes
    :raises ConnectionError: Se houver problemas de conexão com serviços externos

    .. rubric:: Fluxo de execução
    1. Inicialização dos componentes em threads separadas
    2. Validação das configurações
    3. Teste inicial das rotas Flask
    4. Monitoramento contínuo do status
    """
    manager = AppManager()
    try:
        # Validação ANTES de inicializar componentes
        print("🛠️  Verificando configurações básicas...")
        Config.validate()
        print("✅ Configurações válidas")

        # Configurar ambiente
        Config.ENV = "development"
        flask_app = create_app()  # Já registra os blueprints

        # Testar endpoints ANTES de iniciar o servidor
        print("🔥 Testando health check da API...")
        with flask_app.test_client() as client:
            response = client.get(
                "/api/health/",
                headers={"X-API-Key": Config.API_KEY},  # Adicione o header
            )
            assert (
                response.status_code == 200
            ), f"Status inválido: {response.status_code}"
            data = response.get_json()
            assert data["status"] == "healthy", f"Status inválido: {data.get('status')}"
            assert (
                data["environment"] == "development"
            ), f"Ambiente incorreto: {data.get('environment')}"
        print("✅ Testes prévios concluídos")

        atexit.register(manager.graceful_shutdown)
        signal.signal(signal.SIGINT, lambda s, f: manager.graceful_shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: manager.graceful_shutdown())

        # Iniciar componentes APÓS testes
        flask_thread = threading.Thread(target=manager.run_flask_server, daemon=True)
        flask_thread.start()

        manager.tunnel = start_localtunnel()
        if not manager.tunnel:
            raise RuntimeError("Falha ao iniciar o túnel localtunnel")

        manager.flask_app.logger.info(
            "\n✅ Túnel iniciado: %s\n", manager.tunnel["url"]
        )

        # Loop único de monitoramento
        while True:
            if not flask_thread.is_alive():
                raise RuntimeError("Servidor Flask parou inesperadamente")

            if manager.tunnel["process"].poll() is not None:
                raise RuntimeError("Túnel encerrado inesperadamente")

            time.sleep(5)
    except (RuntimeError, ConnectionError, AssertionError) as e:
        if manager and manager.flask_app:
            manager.flask_app.logger.critical("\n❌ Falha crítica:\n%s\n", str(e))
        else:
            print(f"\n❌ Falha crítica:\n{str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
