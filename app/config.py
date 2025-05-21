# app/config.py

"""
Módulo de configuração centralizada para aplicações Flask.

Fornece funcionalidades para:
- Carregamento de variáveis de ambiente
- Configuração avançada de logging
- Validação de ambiente
- Formatação colorida de logs

Classes:
    Config: Configurações principais da aplicação
    ColorFormatter: Formata logs com cores ANSI

Funções:
    configure_logging: Configura sistema de logging da aplicação
"""


import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Any
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Configurações globais da aplicação carregadas de variáveis de ambiente.

    Attributes:
        LOG_FILE (str): Caminho do arquivo de log (padrão: 'app.log')
        ENV (str): Ambiente de execução (development/production)
        SECRET_KEY (str): Chave secreta da aplicação
        WEBHOOK_SECRET (str): Segredo para validação de webhooks
        API_KEY (str): Chave para autenticação de API
        BITRIX_WEBHOOK_URL (str): URL para integração com Bitrix24
        BITRIX_WEBHOOK_TOKEN (str): Token para validação com Bitrix24
        TUNNEL_PORT (int): Porta para túnel reverso (padrão: 5478)
    """

    LOG_FILE: str = "app.log"
    ENV: str = os.getenv("FLASK_ENV", "production").lower()
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    API_KEY: str = os.getenv("API_KEY", "")
    BITRIX_WEBHOOK_URL: str = os.getenv("BITRIX_WEBHOOK_URL", "")
    BITRIX_WEBHOOK_TOKEN: str = os.getenv("BITRIX_WEBHOOK_TOKEN", "")
    TUNNEL_PORT: int = 5478

    @classmethod
    def validate(cls) -> None:
        """
        Valida as variáveis de ambiente obrigatórias.

            :params:
                :cls:  :class:`Config`  # noqa: E1101
                :type:  :class:`Config`

                Classe Config

            :return:
                None

            :raises EnvironmentError: Se variáveis essenciais estiverem faltando
            :raises ValueError: Se variáveis existirem mas estiverem vazias
        """
        required = ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            raise EnvironmentError(f"Variáveis faltando: {', '.join(missing)}")


class ColorFormatter(logging.Formatter):
    """Implementa formatação colorida para logs no terminal usando códigos ANSI.

    Attributes:
        FORMATS (dict): Mapeamento de níveis de log para códigos de cores
    """

    _COLORS = {
        "grey": "\x1b[38;20m",
        "green": "\x1b[32;20m",
        "yellow": "\x1b[33;20m",
        "red": "\x1b[31;20m",
        "bold_red": "\x1b[31;1m",
        "reset": "\x1b[0m",
    }

    _BASE_FORMAT = (
        "%(asctime)s | %(levelname)-8s [%(name)s] | %(module)s:%(lineno)d %(message)s"
    )

    FORMATS = {
        logging.DEBUG: _COLORS["grey"] + _BASE_FORMAT + _COLORS["reset"],
        logging.INFO: _COLORS["green"] + _BASE_FORMAT + _COLORS["reset"],
        logging.WARNING: _COLORS["yellow"] + _BASE_FORMAT + _COLORS["reset"],
        logging.ERROR: _COLORS["red"] + _BASE_FORMAT + _COLORS["reset"],
        logging.CRITICAL: _COLORS["bold_red"] + _BASE_FORMAT + _COLORS["reset"],
    }

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro de log aplicando a cor correspondente ao nível.

        :param record: Registro de log a ser formatado
        :type record: :class:`logging.LogRecord`
        :return: Mensagem de log formatada com cores ANSI
        :rtype: str

        Exemplo de uso:
            >>> formatter = ColorFormatter()
            >>> log_record = logger.makeRecord(
                                "test",
                                logging.INFO,
                                __file__,
                                42,
                                "Test message",
                                (),
                                None
                            )
            >>> colored_message = formatter.format(log_record)
        """
        formatter = logging.Formatter(
            self.FORMATS[record.levelno], datefmt="%Y-%m-%d %H:%M:%S"
        )
        return formatter.format(record)


def configure_logging(app: Any) -> None:
    """Configura o sistema de logging da aplicação.

    Cria:
        - Arquivo de log rotativo
        - Log colorido no console (em desenvolvimento)
        - Estrutura de diretórios para logs

    :param app: Instância da aplicação Flask
    :raises RuntimeError: Em falha crítica de configuração
    """
    try:
        _clean_handlers(app)
        logs_dir = _create_logs_directory()

        file_handler = _create_file_handler(logs_dir)
        app.logger.addHandler(file_handler)

        if Config.ENV == "development":
            _add_console_handler(app)

        _configure_log_levels(app)
        _log_startup_info(app, logs_dir)
        Config.validate()

    except (OSError, IOError) as e:
        raise RuntimeError(f"Falha na configuração de logging: {str(e)}") from e


def _clean_handlers(app: Any) -> None:
    """Remove handlers existentes do logger."""
    app.logger.handlers.clear()


def _create_logs_directory() -> str:
    """Cria diretório de logs com tratamento de erros."""
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def _create_file_handler(logs_dir: str) -> RotatingFileHandler:
    """Configura handler para arquivo de log rotativo."""
    file_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s [%(name)s]\n"
        "PID: %(process)-6d | TID: %(thread)-11d | "
        "%(module)-s.%(funcName)-s Line: %(lineno)-d\n"
        ">> %(message)s\n" + ("-" * 85),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(
        filename=os.path.join(
            logs_dir, f"app_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
        ),
        maxBytes=10 * 1024 * 1024,
        backupCount=0,
        encoding="utf-8",
    )
    handler.setFormatter(file_formatter)  # Correção aplicada aqui

    return handler


def _add_console_handler(app: Any) -> None:
    """Adiciona handler colorido para o console em desenvolvimento."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    console_handler.setLevel(logging.DEBUG)
    app.logger.addHandler(console_handler)


def _configure_log_levels(app: Any) -> None:
    """Define níveis de log conforme ambiente."""
    app.logger.setLevel(logging.DEBUG if Config.ENV == "development" else logging.INFO)
    app.logger.propagate = False


def _log_startup_info(app: Any, logs_dir: str) -> None:
    """Registra informações iniciais no log."""
    log_filename = os.path.join(
        logs_dir, f"app_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )
    app.logger.info(
        "\n%s\n Iniciando aplicação\n Ambiente: %s\n Arquivo de log: %s\n%s\n",
        "#" * 60,
        Config.ENV,
        log_filename,
        "#" * 60,
    )
