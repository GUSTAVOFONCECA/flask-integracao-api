# app/services/conta_azul_auto_auth.py
import time
import logging
import socket
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from app.config import Config

logger = logging.getLogger(__name__)


def find_free_port():
    """Encontra uma porta TCP livre para usar com o Chrome"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def handle_localtunnel_warning(driver):
    """Lida com a página de aviso do LocalTunnel"""
    if (
        "localtunnel" in driver.current_url
        and "This website is served for free via a localtunnel" in driver.page_source
    ):
        logger.info("🛑 Lidando com aviso do LocalTunnel")

        # Localizar elementos
        password_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "tunnel-password-input"))
        )
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")

        # Preencher senha (IP público)
        password_input.send_keys(Config.TUNNEL_PUBLIC_IP)
        submit_button.click()

        # Aguardar redirecionamento
        WebDriverWait(driver, 10).until(EC.url_contains("auth.contaazul.com"))
        logger.info("✅ Aviso do LocalTunnel contornado com sucesso")


def automate_auth():
    """Automatiza o processo de autenticação OAuth2 com Selenium"""
    logger.info("🚀 Iniciando automação de autenticação com Selenium")

    # Verificar se temos o IP público
    if not Config.TUNNEL_PUBLIC_IP:
        logger.error("IP público do túnel não configurado")
        return None

    # Encontrar porta livre
    debug_port = find_free_port()
    logger.info(f"🔌 Usando porta de depuração: {debug_port}")

    # Configurar Chrome
    chrome_options = Options()
    chrome_options.binary_location = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

    chrome_options.add_argument(f"--remote-debugging-port={debug_port}")
    #chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    # Configurar driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Construir URL de autorização
        auth_params = {
            "response_type": "code",
            "client_id": Config.CONTA_AZUL_CLIENT_ID,
            "redirect_uri": Config.CONTA_AZUL_REDIRECT_URI,
            "scope": "openid profile aws.cognito.signin.user.admin",
            "state": "security_token",
        }
        query_string = "&".join([f"{k}={v}" for k, v in auth_params.items()])
        auth_url = f"https://auth.contaazul.com/oauth2/authorize?{query_string}"

        logger.info(f"🌐 Acessando URL de autorização: {auth_url}")
        driver.get(auth_url)

        # Verificar e lidar com aviso do LocalTunnel
        handle_localtunnel_warning(driver)

        # Preencher formulário de login
        logger.info("🔑 Preenchendo formulário de login")
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
        password_field = driver.find_element(By.NAME, "password")
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")

        email_field.send_keys(Config.CONTA_AZUL_EMAIL)
        password_field.send_keys(Config.CONTA_AZUL_PASSWORD)
        submit_button.click()

        # Lidar com aprovação do aplicativo
        time.sleep(3)
        if "oauth2/authorize" in driver.current_url:
            logger.info("✅ Autorizando aplicativo")
            try:
                allow_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(., 'Allow')]")
                    )
                )
                allow_button.click()
            except Exception:
                logger.info("ℹ️ Nenhum prompt de autorização encontrado")

        # Aguardar redirecionamento para callback
        WebDriverWait(driver, 20).until(
            lambda d: Config.CONTA_AZUL_REDIRECT_URI in d.current_url
        )

        # Extrair código de autorização
        parsed_url = urlparse(driver.current_url)
        query_params = parse_qs(parsed_url.query)
        auth_code = query_params.get("code", [None])[0]

        if not auth_code:
            raise ValueError("❌ Código de autorização não encontrado")

        logger.info(f"🔑 Código de autorização obtido: {auth_code}")
        return auth_code

    except Exception as e:
        logger.error(f"❌ Falha na automação de autenticação: {str(e)}")
        # Capturar screenshot para debug
        driver.save_screenshot("auth_error.png")
        logger.error("📸 Screenshot salvo em auth_error.png")
        return None
    finally:
        driver.quit()
        logger.info("🛑 Navegador fechado")
