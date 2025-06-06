# app/services/conta_azul_auto_auth.py
import time
import logging
import socket
from urllib.parse import urlparse, parse_qs, urlencode
from selenium_stealth import stealth
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from app.config import Config
from app.utils import save_page_diagnosis

logger = logging.getLogger(__name__)

# Endpoints da Conta Azul
AUTH_URL = "https://auth.contaazul.com/oauth2/authorize"


def find_free_port():
    """Encontra uma porta TCP livre para usar com o Chrome"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def handle_localtunnel_warning(driver):
    """Lida com a página de aviso do LocalTunnel de forma mais robusta"""
    try:
        # Verificação mais confiável da página do LocalTunnel
        if "localtunnel" in driver.current_url:
            password_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "tunnel-password-input"))
            )
            logger.info("🛑 Detectada página de aviso do LocalTunnel")

            # Preencher senha (IP público)
            password_input.clear()
            password_input.send_keys(Config.TUNNEL_PUBLIC_IP)

            # Localizar botão de submit de forma mais robusta
            submit_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(text(), 'Acessar') or contains(text(), 'Submit')]",
                    )
                )
            )
            submit_button.click()

            # Aguardar redirecionamento com timeout maior
            WebDriverWait(driver, 15).until(
                lambda d: "auth.contaazul.com" in d.current_url
            )
            logger.info("✅ Aviso do LocalTunnel contornado com sucesso")
            return True
    except (TimeoutException, NoSuchElementException):
        logger.info("ℹ️ Página de aviso do LocalTunnel não detectada")
    return False


def get_auth_url(state: str = "security_token") -> str:
    """Retorna a URL de autorização para redirecionar o usuário."""
    params = {
        "response_type": "code",
        "client_id": Config.CONTA_AZUL_CLIENT_ID,
        "redirect_uri": Config.CONTA_AZUL_REDIRECT_URI,
        "scope": "openid profile aws.cognito.signin.user.admin",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


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
    chrome_options.binary_location = (
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    )

    chrome_options.add_argument(f"--remote-debugging-port={debug_port}")
    chrome_options.add_argument("start-maximized")
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )  # Configurar driver

    # Definir a propriedade do navegador "webdriver" para undefined
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    try:
        auth_url = get_auth_url()
        logger.info(f"🌐 Acessando URL de autorização: {auth_url}")
        driver.get(auth_url)

        # Verificar e lidar com aviso do LocalTunnel
        localtunnel_detected = handle_localtunnel_warning(driver)

        # Se o LocalTunnel foi detectado, esperar o carregamento da página de login
        if localtunnel_detected:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "signInFormUsername"))
            )

        # Identificar formulário VISÍVEL (desktop)
        login_form = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR,
                ".modal-content.visible-md.visible-lg:not([style*='display: none'])"
            ))
        )
        logger.info("✅ Formulário desktop visível encontrado")

        # Preencher formulário de login
        logger.info("🔑 Preenchendo formulário de login")
        email_field = login_form.find_element(By.ID, "signInFormUsername")
        password_field = login_form.find_element(By.ID, "signInFormPassword")
        submit_button = login_form.find_element(By.NAME, "signInSubmitButton")

        email_field.send_keys(Config.CONTA_AZUL_EMAIL)
        time.sleep(0.5)  # Espera para a interface responder

        password_field.send_keys(Config.CONTA_AZUL_PASSWORD)
        time.sleep(0.5)  # Espera para a interface responder

        driver.execute_script("arguments[0].click();", submit_button)
        try:
            WebDriverWait(driver, 10).until(
                EC.any_of(
                    EC.url_contains("auth.contaazul.com/oauth2/authorize"),
                    EC.url_contains(Config.CONTA_AZUL_REDIRECT_URI),
                )
            )
        except TimeoutException as e:
            # Salvar diagnóstico detalhado
            log_file = save_page_diagnosis(driver, e)
            logger.error(f"Redirecionamento não ocorreu após o login. Diagnóstico salvo em: {log_file}")
            return None

        # Lidar com aprovação do aplicativo
        time.sleep(3)
        if "oauth2/authorize" in driver.current_url:
            logger.info("✅ Autorizando aplicativo")
            try:
                allow_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(., 'Allow')]")
                    )
                )
                allow_button.click()
            except Exception as e:
                # Salvar diagnóstico detalhado
                log_file = save_page_diagnosis(driver, e)
                logger.info(f"ℹ️ Nenhum prompt de autorização encontrado. Diagnóstico salvo em: {log_file}")

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
        # Salvar diagnóstico detalhado
        log_file = save_page_diagnosis(driver, e)
        logger.error(f"❌ Elemento não encontrado. Diagnóstico salvo em: {log_file}")
        return None
    finally:
        driver.quit()
        logger.info("🛑 Navegador fechado")
