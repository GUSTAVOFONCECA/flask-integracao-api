# app/config.py
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()


class Config:
    ENV = os.getenv("FLASK_ENV", "production").lower()
    SECRET_KEY = os.getenv("SECRET_KEY")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    API_KEY = os.getenv("API_KEY")
    BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
    TUNNEL_PORT = 5478

    @classmethod
    def validate(cls):
        required = ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            raise EnvironmentError(f"Variáveis faltando: {', '.join(missing)}")


class ColorFormatter(logging.Formatter):
    """Formatação colorida para o terminal"""

    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    FORMAT = "%(asctime)s | %(levelname)-8s [%(name)s] | %(module)s:%(lineno)d %(message)s"
    FORMATS = {
        logging.DEBUG: grey + FORMAT + reset,
        logging.INFO: green + FORMAT + reset,
        logging.WARNING: yellow + FORMAT + reset,
        logging.ERROR: red + FORMAT + reset,
        logging.CRITICAL: bold_red + FORMAT + reset,
    }

    def format(self, record):
        formatter = logging.Formatter(
            self.FORMATS[record.levelno], datefmt="%Y-%m-%d %H:%M:%S"
        )
        return formatter.format(record)


def configure_logging(app):
    """Configuração avançada de logging"""
    try:
        # Limpar handlers existentes
        app.logger.handlers.clear()

        # Criar diretório de logs
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)

        # Configurar formato do arquivo (corrigido)
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s]\n"
            "PID: %(process)-6d | TID: %(thread)-11d | %(module)-s.%(funcName)-s Line: %(lineno)-d\n"
            ">> %(message)s\n"
            f"{"-" * 85}",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File Handler
        file_handler = RotatingFileHandler(
            filename=os.path.join(
                logs_dir, f"app_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
            ),
            maxBytes=10 * 1024 * 1024,
            backupCount=0,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)

        # Console Handler (só adicionar se não existir)
        if Config.ENV == "development" and not any(
            isinstance(h, logging.StreamHandler) for h in app.logger.handlers
        ):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorFormatter())
            console_handler.setLevel(logging.DEBUG)
            app.logger.addHandler(console_handler)

        # Adicionar handlers
        if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
            app.logger.addHandler(file_handler)

        # Configurar níveis
        app.logger.setLevel(
            logging.DEBUG if Config.ENV == "development" else logging.INFO
        )
        app.logger.propagate = False  # Impedir propagação para loggers pai

        # Nome do arquivo com timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = os.path.join(logs_dir, f"app_{timestamp}.log")

        # Log inicial
        app.logger.info(
            f"\n{'#' * 60}\n"
            f" Iniciando aplicação\n"
            f" Ambiente: {Config.ENV}\n"
            f" Arquivo de log: {log_filename}\n"
            f"{'#' * 60}\n"
        )

        # Validar configuração
        Config.validate()

    except Exception as e:
        print(f"\n❌ Falha crítica na configuração:\n{str(e)}\n")
        sys.exit(1)
