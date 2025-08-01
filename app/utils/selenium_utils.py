# app/utils/selenium_utils.py
"""
Selenium utilities following Single Responsibility Principle.
Handles Selenium-specific operations.
"""

import os
import datetime
import logging
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class SeleniumDiagnosticTool:
    """
    Selenium diagnostic tool following Single Responsibility Principle.
    Handles page diagnosis and debugging.
    """

    @staticmethod
    def save_page_diagnosis(driver, exception, filename_prefix="element_error"):
        """Salva diagnóstico completo da página quando ocorre falha com elementos"""
        # Criar diretório de logs se não existir
        log_dir = "selenium_diagnostics"
        os.makedirs(log_dir, exist_ok=True)

        # Nome do arquivo com timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{log_dir}/{filename_prefix}_{timestamp}"

        # Salvar screenshot
        driver.save_screenshot(f"{filename}.png")

        # Salvar HTML da página
        with open(f"{filename}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        # Coletar informações de elementos
        element_info = []

        # Informações básicas da página
        element_info.append("=" * 80)
        element_info.append(f"Diagnóstico da Página - {timestamp}")
        element_info.append("=" * 80)
        element_info.append(f"URL: {driver.current_url}")
        element_info.append(f"Título: {driver.title}")
        element_info.append(f"Exceção: {type(exception).__name__}: {str(exception)}")
        element_info.append("\n" + "=" * 80)
        element_info.append("ESTADO DOS ELEMENTOS-CHAVE")
        element_info.append("=" * 80)

        # Verificar elementos importantes
        key_elements = {
            "username_field": "input[name='username']",
            "password_field": "input[name='password']",
            "submit_button": "input[name='signInSubmitButton']",
            "login_form": "form[name='cognitoSignInForm']",
            "iframe": "iframe",
            "local_tunnel_warning": "#tunnel-password-input",
        }

        for name, selector in key_elements.items():
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                element_info.append(f"{name.upper()} ({selector})")
                element_info.append(f"  Encontrados: {len(elements)} elementos")

                for i, element in enumerate(elements, 1):
                    state = []
                    try:
                        state.append(
                            f"Visível: {'Sim' if element.is_displayed() else 'Não'}"
                        )
                        state.append(
                            f"Habilitado: {'Sim' if element.is_enabled() else 'Não'}"
                        )
                        state.append(
                            f"Texto: {element.text[:50] + '...' if element.text else 'N/A'}"
                        )
                        state.append(
                            f"Valor: {element.get_attribute('value')[:50] + '...' if element.get_attribute('value') else 'N/A'}"
                        )
                    except Exception as e:
                        state.append(f"Erro ao verificar estado: {str(e)}")

                    element_info.append(f"  Elemento {i}:")
                    element_info.extend([f"    {s}" for s in state])

            except Exception as e:
                element_info.append(f"ERRO ao verificar {name}: {str(e)}")

        # Informações gerais sobre a página
        element_info.append("\n" + "=" * 80)
        element_info.append("ESTRUTURA GERAL DA PÁGINA")
        element_info.append("=" * 80)

        try:
            # Contagem de elementos por tipo
            element_counts = {
                "formulários": "form",
                "inputs": "input",
                "botões": "button",
                "iframes": "iframe",
                "divs": "div",
            }

            for desc, selector in element_counts.items():
                count = len(driver.find_elements(By.CSS_SELECTOR, selector))
                element_info.append(f"{desc.capitalize()}: {count}")

            # Estrutura de títulos
            element_info.append("\nCabeçalhos:")
            for level in range(1, 7):
                headers = driver.find_elements(By.CSS_SELECTOR, f"h{level}")
                element_info.append(f"  H{level}: {len(headers)} encontrados")

        except Exception as e:
            element_info.append(f"Erro ao analisar estrutura: {str(e)}")

        # Salvar diagnóstico em TXT
        with open(f"{filename}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(element_info))

        return filename
