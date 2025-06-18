# app/config.py

"""
Módulo de configuração centralizada para a aplicação Flask.

- Carrega variáveis de ambiente (python-dotenv).
- Configura logging em arquivo (RotatingFileHandler) e console (StreamHandler com cores).
- Garante que todos os logs (INFO, DEBUG, WARNING, ERROR) sejam gravados em arquivo.
- Valida variáveis obrigatórias: SECRET_KEY, WEBHOOK_SECRET, API_KEY.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Any
from dotenv import load_dotenv

# 1) Carrega variáveis do .env (se existir)
load_dotenv()


class Config:
    """
    Configurações globais da aplicação (lidas via .env ou padrão).
    """

    # Ambiente de execução: 'development' ou 'production'
    ENV: str = os.getenv("FLASK_ENV", "production").lower()

    # Variáveis obrigatórias
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    API_KEY: str = os.getenv("API_KEY", "")

    # Porta para túnel reverso (LocalTunnel, ngrok, etc.)
    TUNNEL_PORT: int = int(os.getenv("TUNNEL_PORT", "5478"))

    # Bitrix24 env
    BITRIX_WEBHOOK_URL: str = os.getenv("BITRIX_WEBHOOK_URL", "")
    BITRIX_WEBHOOK_TOKEN: str = os.getenv("BITRIX_WEBHOOK_TOKEN", "")

    # Digisac env
    DIGISAC_USER: str = os.getenv("DIGISAC_USER", "")
    DIGISAC_PASSWORD: str = os.getenv("DIGISAC_PASSWORD", "")
    DIGISAC_USER_ID: str = os.getenv("DIGISAC_USER_ID", "")
    DIGISAC_TOKEN: str = os.getenv("DIGISAC_TOKEN", "")

    # Conta Azul env
    CONTA_AZUL_CLIENT_ID: str = os.getenv("CONTA_AZUL_CLIENT_ID", "")
    CONTA_AZUL_CLIENT_SECRET: str = os.getenv("CONTA_AZUL_CLIENT_SECRET", "")
    CONTA_AZUL_REDIRECT_URI: str = os.getenv(
        "CONTA_AZUL_REDIRECT_URI", "https://127.0.0.1:5478/conta-azul/callback"
    )
    CONTA_AZUL_EMAIL: str = os.getenv("CONTA_AZUL_EMAIL", "")
    CONTA_AZUL_PASSWORD: str = os.getenv("CONTA_AZUL_PASSWORD", "")
    CONTA_AZUL_CONTA_BANCARIA_UUID: str = os.getenv("CONTA_AZUL_CONTA_BANCARIA_UUID", "")
    CHROMEDRIVER_PATH: str = os.path.join(os.getcwd(), "chromedriver-win64", "chromedriver.exe")
    TUNNEL_PUBLIC_IP: str = None

    @classmethod
    def validate(cls) -> None:
        """
        Verifica se as variáveis obrigatórias estão preenchidas.
        Caso contrario, lança EnvironmentError.
        """
        required = ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            raise EnvironmentError(
                f"Variáveis obrigatórias faltando: {', '.join(missing)}"
            )


class ColorFormatter(logging.Formatter):
    """
    Formata registros de log no console com cores ANSI, emojis e quebras de linha.

    Exibe:
     - DEBUG em cinza 🐛
     - INFO em verde ℹ️
     - WARNING em amarelo ⚠️
     - ERROR em vermelho 🛑
     - CRITICAL em vermelho negrito 💥
    """

    _COLORS = {
        logging.DEBUG: "\x1b[38;5;244m",  # cinza claro
        logging.INFO: "\x1b[32;20m",  # verde
        logging.WARNING: "\x1b[33;20m",  # amarelo
        logging.ERROR: "\x1b[31;20m",  # vermelho
        logging.CRITICAL: "\x1b[31;1m",  # vermelho negrito
        "reset": "\x1b[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Retorna uma string composta por:
         - Timestamp
         - Levelname
         - [Nome do logger]
         - Módulo:linha
         - Mensagem (precedida por emoji)
         - Linha de separação
        Tudo colorido conforme o level.
        """
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        lvl = record.levelno

        if lvl == logging.DEBUG:
            color = self._COLORS[lvl]
            emoji = "🐛 "
        elif lvl == logging.INFO:
            color = self._COLORS[lvl]
            emoji = "ℹ️ "
        elif lvl == logging.WARNING:
            color = self._COLORS[lvl]
            emoji = "⚠️ "
        elif lvl == logging.ERROR:
            color = self._COLORS[lvl]
            emoji = "🛑 "
        elif lvl == logging.CRITICAL:
            color = self._COLORS[lvl]
            emoji = "💥 "
        else:
            color = ""
            emoji = ""

        # Formato multilinha:
        base = (
            f"\n{ts} | {record.levelname:<8} | [{record.name}] | "
            f"{record.module}:{record.lineno}\n"
            f"{emoji} {record.getMessage()}\n" + "-" * 80
        )
        return f"{color}{base}{self._COLORS['reset']}"


def configure_logging(app: Any) -> None:
    """
    Configura o sistema de logging:

    1) Cria pasta absoluta "logs/" dentro da raiz do projeto.
    2) Cria RotatingFileHandler (NÍVEL MÍNIMO: DEBUG) gravando em arquivo.
    3) Cria StreamHandler (para console) com ColorFormatter.
       - DEBUG+ no console se ENV == "development"
       - INFO+ no console se ENV == "production"
    4) Anexa esses handlers ao root logger, para que todos os sub-loggers herdem.
    5) Ajusta níveis de log para werkzeug e urllib3 (não poluir).
    6) Ajusta app.logger para não propagar duplicadamente.
    7) Lança um log inicial de “startup” com informações de ambiente + caminho do arquivo.
    8) Valida variáveis obrigatórias.
    """
    try:
        # >>> 1) Diretório absoluto para logs <<<
        # Assumimos que este script está em "app/config.py".
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_dir = os.path.join(project_root, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # >>> 2) RotatingFileHandler (DEBUG+) <<<
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(logs_dir, f"app_{timestamp}.log")

        file_handler = RotatingFileHandler(
            filename=filename,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        # Formato de arquivo: multilinha, sem cores
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s | [%(name)s] | %(module)s:%(lineno)d\n"
            "→ %(message)s\n" + ("=" * 100),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # grava TUDO a partir de DEBUG

        # >>> 3) StreamHandler para console <<<
        console_handler = logging.StreamHandler()
        lvl = logging.DEBUG if Config.ENV == "development" else logging.INFO
        console_handler.setLevel(lvl)
        console_handler.setFormatter(ColorFormatter())

        # >>> 4) Root logger <<<
        root_logger = logging.getLogger()  # logger raiz
        root_logger.setLevel(logging.DEBUG)  # captura TUDO
        # Remove handlers antigos (se houver) para evitar duplicação
        for h in list(root_logger.handlers):
            root_logger.removeHandler(h)
        # Adiciona os novos
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        # >>> 5) Silenciar bibliotecas muito verbosas <<<
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        # >>> 6) Log inicial de startup <<<
        app.logger.info(
            "🚀 🚀 🚀  Iniciando aplicação Flask  🚀 🚀 🚀\n"
            f"   Ambiente : {Config.ENV.upper()}\n"
            f"   Log File : {filename}\n" + ("=" * 100)
        )

        # >>> 7) Validação de variáveis obrigatórias <<<
        Config.validate()

    except Exception as e:
        # Se qualquer coisa falhar, encerra imediatamente
        raise RuntimeError(f"Falha ao configurar logging: {e}") from e
