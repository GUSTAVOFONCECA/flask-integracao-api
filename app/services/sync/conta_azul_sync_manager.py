# app/services/sync/conta_azul_sync_manager.py
import os
from app.services.sync.base import BaseSyncManager
from app.services.conta_azul.conta_azul_services import (
    get_auth_headers_conta_azul as get_ca_headers,
)

# Relpaths dentro de app/database/conta_azul/
PERSON_PATH = os.path.join("conta_azul", "person.json")
ACCOUNT_PATH = os.path.join("conta_azul", "accounts.json")
SERVICE_PATH = os.path.join("conta_azul", "services.json")

PERSON_STATE = os.path.join("conta_azul", "person_state.json")
ACCOUNT_STATE = os.path.join("conta_azul", "accounts_state.json")
SERVICE_STATE = os.path.join("conta_azul", "services_state.json")


class PersonsSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 10):
        super().__init__(
            entity="CA::Pessoas",
            endpoint="https://api-v2.contaazul.com/v1/pessoa",
            headers_func=get_ca_headers,
            params_template={"tipo_perfil": "CLIENTE", "status": "ATIVO"},
            page_param="pagina",
            page_size_param="tamanho_pagina",
            page_size=page_size,
            data_relpath=PERSON_PATH,
            state_relpath=PERSON_STATE,
            list_key="itens",
        )


class AccountsSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 10):
        super().__init__(
            entity="CA::Contas",
            endpoint="https://api-v2.contaazul.com/v1/conta-financeira",
            headers_func=get_ca_headers,
            params_template={"apenas_ativo": "true"},
            page_param="pagina",
            page_size_param="tamanho_pagina",
            page_size=page_size,
            data_relpath=ACCOUNT_PATH,
            state_relpath=ACCOUNT_STATE,
            list_key="itens",
        )


class ServicesSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 10):
        super().__init__(
            entity="CA::Servicos",
            endpoint="https://api-v2.contaazul.com/v1/servicos",
            headers_func=get_ca_headers,
            params_template={},
            page_param="pagina",
            page_size_param="tamanho_pagina",
            page_size=page_size,
            data_relpath=SERVICE_PATH,
            state_relpath=SERVICE_STATE,
            list_key="itens",
        )
