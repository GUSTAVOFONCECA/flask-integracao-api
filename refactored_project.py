# Project layout:
# integrations/
#   conta_azul/
#     auto_auth.py
#     client.py
#     sync.py
#     match.py
#     sales.py
#   digisac/
#     client.py
# webhooks/
#   routes.py

# ------------------------------
# integrations/conta_azul/auto_auth.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs
from .client import get_auth_url
from .utils import save_page_diagnosis, find_free_port
import time
import logging

logger = logging.getLogger(__name__)


def automate_auth(driver_timeout=180):
    """Automatiza o OAuth2 com Selenium e 2FA"""
    driver = _create_stealth_driver()
    try:
        auth_url = get_auth_url()
        logger.info(f"🌐 Acessando URL: {auth_url}")
        driver.get(auth_url)

        # handle initial login form
        _handle_login_form(driver)

        # handle optional 2FA
        _handle_2fa_if_present(driver, timeout=driver_timeout)

        # wait for real callback redirect
        redirect_uri = driver.current_url.split('?')[0]
        WebDriverWait(driver, driver_timeout).until(
            lambda d: redirect_uri == d.current_url.split('?')[0]
        )

        # extract code
        parsed = urlparse(driver.current_url)
        code = parse_qs(parsed.query).get('code', [None])[0]
        if not code:
            raise ValueError("Código de autorização não encontrado")
        return code
    except Exception as e:
        save_page_diagnosis(driver, e)
        raise
    finally:
        driver.quit()


def _create_stealth_driver():
    chrome_options = Options()
    port = find_free_port()
    chrome_options.add_argument(f"--remote-debugging-port={port}")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _handle_login_form(driver):
    wait = WebDriverWait(driver, 20)
    form = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "form#loginForm")))
    form.find_element(By.ID, "username").send_keys(Config.EMAIL)
    form.find_element(By.ID, "password").send_keys(Config.PASSWORD)
    form.find_element(By.NAME, "submit").click()


def _handle_2fa_if_present(driver, timeout=180):
    try:
        wait = WebDriverWait(driver, 10)
        twofa = wait.until(EC.presence_of_element_located((By.NAME, 'authentication_code')))
        logger.info("2FA detected, waiting for user input...")
        WebDriverWait(driver, timeout).until(EC.staleness_of(twofa))
    except Exception:
        logger.debug("2FA not required or already handled.")


# ------------------------------
# integrations/conta_azul/client.py
import os
import base64
import requests
from datetime import datetime, timedelta
from flask import current_app

AUTH_URL = "https://auth.contaazul.com/oauth2/authorize"
TOKEN_URL = "https://auth.contaazul.com/oauth2/token"
API_BASE = "https://api-v2.contaazul.com"

def get_auth_url(state='security_token'):
    cfg = current_app.config
    params = {
        'response_type': 'code',
        'client_id': cfg['CONTA_AZUL_CLIENT_ID'],
        'redirect_uri': cfg['CONTA_AZUL_REDIRECT_URI'],
        'scope': 'openid profile aws.cognito.signin.user.admin',
        'state': state
    }
    return f"{AUTH_URL}?{urlencode(params)}"

_conta_azul_tokens = {}


def get_tokens(code):
    cfg = current_app.config
    cred = f"{cfg['CONTA_AZUL_CLIENT_ID']}:{cfg['CONTA_AZUL_CLIENT_SECRET']}"
    b64 = base64.b64encode(cred.encode()).decode()
    resp = requests.post(TOKEN_URL,
        data={'grant_type':'authorization_code','code':code,'redirect_uri':cfg['CONTA_AZUL_REDIRECT_URI']},
        headers={'Authorization': f'Basic {b64}'}
    )
    resp.raise_for_status()
    return resp.json()


def refresh_tokens():
    cfg = current_app.config
    b64 = base64.b64encode(f"{cfg['CONTA_AZUL_CLIENT_ID']}:{cfg['CONTA_AZUL_CLIENT_SECRET']}".encode()).decode()
    resp = requests.post(TOKEN_URL,
        data={'grant_type':'refresh_token','refresh_token':_conta_azul_tokens.get('refresh_token')},
        headers={'Authorization': f'Basic {b64}'}
    )
    resp.raise_for_status()
    return resp.json()


def get_auth_headers():
    global _conta_azul_tokens
    if not _conta_azul_tokens or datetime.utcnow() >= _conta_azul_tokens.get('expires_at'):
        data = refresh_tokens()
        set_tokens(data)
    return {'Authorization': f"Bearer {_conta_azul_tokens['access_token']}"}


def set_tokens(data):
    data['expires_at'] = datetime.utcnow() + timedelta(seconds=data['expires_in'])
    _conta_azul_tokens.update(data)


def create_sale(payload: dict):
    resp = requests.post(f"{API_BASE}/v1/venda", json=payload, headers=get_auth_headers())
    resp.raise_for_status()
    return resp.json()


def get_sales(page=1,size=100):
    resp = requests.get(f"{API_BASE}/v1/venda", params={'page':page,'size':size}, headers=get_auth_headers())
    resp.raise_for_status()
    return resp.json()

# ... further methods ...

# ------------------------------
# integrations/conta_azul/sync.py
import os
import json
import requests
from datetime import datetime

class SyncManager:
    def __init__(self, name, api_url, auth_headers_func, params, base_path='database/conta_azul', page_size=10):
        self.name = name
        self.url = api_url
        self.headers = auth_headers_func
        self.params = params
        self.page_size = page_size
        self.data_file = f"{base_path}/{name}.json"
        self.state_file = f"{base_path}/{name}_state.json"
        os.makedirs(base_path, exist_ok=True)
        self._load()

    def _load(self):
        self.page = 1
        self.data = []
        if os.path.exists(self.state_file):
            st = json.load(open(self.state_file))
            self.page = st.get('last_page',1)
            self.data = json.load(open(self.data_file,'r'))

    def _save(self):
        json.dump({'last_page':self.page}, open(self.state_file,'w'), indent=2)
        json.dump(self.data, open(self.data_file,'w',encoding='utf-8'), indent=2, ensure_ascii=False)

    def run(self):
        while True:
            p = dict(self.params, pagina=self.page, tamanho_pagina=self.page_size)
            items = requests.get(self.url, headers=self.headers(), params=p).json().get('itens',[])
            if not items: break
            self.data.extend(items)
            self._save()
            if len(items)<self.page_size: break
            self.page+=1

# ------------------------------
# integrations/conta_azul/match.py
import json
import re

def normalize_phone(phone): return re.sub(r'\D','',phone or '')

def find_person_by_phone(phone, persons_path='database/conta_azul/pessoas.json'):
    data = json.load(open(persons_path,'r',encoding='utf-8'))
    key = normalize_phone(phone)
    for p in data.get('itens',[]):
        if normalize_phone(p.get('telefone'))==key:
            return p['uuid']
    return None

# ------------------------------
# integrations/conta_azul/sales.py
from datetime import datetime, timedelta
from .client import create_sale

SERVICOS = {
    'Pessoa jurídica': ('0b4f9a8b-01bb-4a89-93b3-7f56210bc75d','CERTIFICADO DIGITAL PJ',180),
    'Pessoa física - CPF':('586d5eb2-23aa-47ff-8157-fd85de8b9932','CERTIFICADO DIGITAL PF',130),
    'Pessoa física - CEI':('586d5eb2-23aa-47ff-8157-fd85de8b9932','CERTIFICADO DIGITAL PF',130)
}

def build_sale_params(deal_type):
    if deal_type not in SERVICOS:
        raise ValueError(f"Tipo inválido {deal_type}")
    sid, desc, price = SERVICOS[deal_type]
    now = datetime.utcnow()
    return {
        'id_service': sid,
        'item_description': desc,
        'price': price,
        'sale_date': now,
        'due_date': now + timedelta(days=5)
    }


def handle_sale_creation(contact_number, deal_type, match_func, client_lookup):
    pid = client_lookup(contact_number)
    if not pid: raise ValueError("Cliente não encontrado")
    params = build_sale_params(deal_type)
    payload = {
        'id_cliente': pid,
        'situacao':'APROVADO',
        'data_venda': params['sale_date'].strftime("%Y-%m-%d"),
        'itens':[{
            'descricao':params['item_description'],
            'quantidade':1,
            'valor':params['price'],
            'id':params['id_service']
        }],
        'condicao_pagamento':{
            'tipo_pagamento':'BOLETO_BANCARIO',
            'id_conta_financeira':current_app.config['CONTA_AZUL_FINANCE_ACCOUNT_ID'],
            'opcao_condicao_pagamento':'À vista',
            'parcelas':[{
                'data_vencimento':params['due_date'].strftime("%Y-%m-%d"),
                'valor':params['price'],
                'descricao':'Parcela única'
            }]
        }
    }
    return create_sale(payload)

# ------------------------------
# integrations/digisac/client.py
import requests
from flask import current_app

def get_digisac_headers():
    cfg = current_app.config
    token = cfg['DIGISAC_TOKEN']
    return {'Authorization':f'Bearer {token}','Content-Type':'application/json'}

# funções send_message, transfer_ticket, get_contact_by_number...

# ------------------------------
# webhooks/routes.py
from flask import Blueprint, request, jsonify
from integrations.conta_azul.match import find_person_by_phone
from integrations.conta_azul.sales import handle_sale_creation

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')

@bp.route('/aviso-certificado', methods=['GET','POST'])
def aviso_certificado():
    num = request.args.get('contactNumber')
    deal = request.args.get('dealType')
    try:
        result = handle_sale_creation(num, deal, find_person_by_phone, find_person_by_phone)
        return jsonify(result),200
    except Exception as e:
        return jsonify({'error':str(e)}),400
