"""
Configuração do aplicativo Flask com logging avançado e validação de ambiente.
Esta configuração inclui:
- Carregamento de variáveis de ambiente usando dotenv.
- Configuração de logging com formatação colorida para o terminal e arquivo.
- Validação de variáveis de ambiente obrigatórias.
- Configuração de um manipulador de log rotativo para arquivos.
- Configuração de um manipulador de log para o console em modo de desenvolvimento.
- Validação de configuração no início do aplicativo.
- Tratamento de exceções durante a configuração.
# Configuração de logging avançada
- Limpeza de manipuladores de log existentes.
- Criação de diretório de logs se não existir.
- Configuração de formato de log para arquivo e console.
- Configuração de níveis de log para diferentes ambientes (desenvolvimento e produção).
- Registro de informações iniciais no log, incluindo ambiente e arquivo de log.
- Tratamento de exceções durante a configuração de logging.
- Validação de configuração no início do aplicativo.
"""

# app/config.py
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class Config:
    LOG_FILE: str = "app.log"
    ENV = os.getenv("FLASK_ENV", "production").lower()
    SECRET_KEY = os.getenv("SECRET_KEY")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    API_KEY = os.getenv("API_KEY")
    BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
    TUNNEL_PORT = 5478

    @classmethod
    def validate(cls):
        """
        Valida as variáveis de ambiente obrigatórias.
        Lança um erro se alguma variável obrigatória estiver faltando.

            :params:
                :cls:  :class:`Config`  # noqa: E1101
                :type:  :class:`Config`

                Classe Config

            :return:
                None

            :raises EnvironmentError: Se alguma variável obrigatória estiver faltando.
            :raises TypeError: Se alguma variável obrigatória não for do tipo string.
            :raises ValueError: Se alguma variável obrigatória estiver vazia.
        """
        required = ["SECRET_KEY", "WEBHOOK_SECRET", "API_KEY"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            raise EnvironmentError(f"Variáveis faltando: {', '.join(missing)}")


class ColorFormatter(logging.Formatter):
    """Formata mensagens de log com cores ANSI para saída no terminal.
      
    Esta classe herda de :class:`logging.Formatter` e adiciona cores ANSI para diferentes
    níveis de log. Atribui esquemas de cores distintos para DEBUG, INFO, WARNING, ERROR e CRITICAL.

    :ivar grey: Código ANSI para texto cinza, defaults to "\x1b[38;20m"
    :vartype grey: str, optional
    :ivar green: Código ANSI para texto verde, defaults to "\x1b[32;20m"
    :vartype green: str, optional
    :ivar yellow: Código ANSI para texto amarelo, defaults to "\x1b[33;20m"
    :vartype yellow: str, optional
    :ivar red: Código ANSI para texto vermelho, defaults to "\x1b[31;20m"
    :vartype red: str, optional
    :ivar bold_red: Código ANSI para texto vermelho em negrito, defaults to "\x1b[31;1m"
    :vartype bold_red: str, optional
    :ivar reset: Código ANSI para resetar formatação, defaults to "\x1b[0m"
    :vartype reset: str, optional
    :ivar FORMAT: Template base para formatação das mensagens, defaults to 
        "%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d - %(message)s"
    :vartype FORMAT: str, optional
    :ivar FORMATS: Mapeamento de formatos por nível de logging, defaults to dicionário
        com combinações de cores por nível
    :vartype FORMATS: dict, optional
    """
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    FORMAT = (
        "%(asctime)s | %(levelname)-8s [%(name)s] | %(module)s:%(lineno)d %(message)s"
    )
    FORMATS = {
        logging.DEBUG: grey + FORMAT + reset,
        logging.INFO: green + FORMAT + reset,
        logging.WARNING: yellow + FORMAT + reset,
        logging.ERROR: red + FORMAT + reset,
        logging.CRITICAL: bold_red + FORMAT + reset,
    }

    def format(self, record):
        """Formata o registro de log aplicando a cor correspondente ao nível.
        
        :param record: Registro de log a ser formatado
        :type record: :class:`logging.LogRecord`
        :return: Mensagem de log formatada com cores ANSI
        :rtype: str
        :raises ValueError: Se o nível de log não estiver mapeado em FORMATS
        
        Exemplo de uso:
            >>> formatter = ColorFormatter()
            >>> log_record = logger.makeRecord("test", logging.INFO, __file__, 42, "Test message", (), None)
            >>> colored_message = formatter.format(log_record)
        """
        formatter = logging.Formatter(
            self.FORMATS[record.levelno], datefmt="%Y-%m-%d %H:%M:%S"
        )
        return formatter.format(record)


def configure_logging(app):
    """
    Configura o sistema de logging da aplicação com handlers para arquivo e console.
    Cria estrutura de diretórios e arquivos de log com formatação específica.

        :params:
            :app: :class:`Flask`
                Instância da aplicação Flask

        :return:
            None

        :raises OSError: Se falhar ao criar diretório de logs
        :raises IOError: Se falhar ao escrever no arquivo de log
        :raises EnvironmentError: Se ocorrer erro geral de ambiente
    """
    try:
        # Limpar handlers existentes
        app.logger.handlers.clear()

        # Criar diretório de logs
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)

        # Configurar formato do arquivo (corrigido)
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s]\n"
            "PID: %(process)-6d | TID: %(thread)-11d | "
            "%(module)-s.%(funcName)-s Line: %(lineno)-d\n"
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

    except (OSError, IOError, EnvironmentError) as e:
        print(f"\n❌ Falha crítica na configuração:\n{str(e)}\n")
        sys.exit(1)
