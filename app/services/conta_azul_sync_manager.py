import os
import json
import requests
from datetime import datetime

class SyncManager:
    """
    Gerencia sincronização de entidades da API da Conta Azul.
    Persistência de dados em JSON e progresso em arquivo de estado.
    Garante que pastas necessárias existam antes de salvar.
    """
    def __init__(
        self,
        entity_name: str,
        api_url: str,
        auth_headers_func,
        params_template: dict,
        data_filename: str = None,
        state_filename: str = None,
        page_param: str = "pagina",
        page_size_param: str = "tamanho_pagina",
        page_size: int = 10,
    ):
        self.entity = entity_name
        self.api_url = api_url
        self.auth_headers = auth_headers_func
        self.params_template = params_template.copy()
        self.page_param = page_param
        self.page_size_param = page_size_param
        self.page_size = page_size
        self.data_filename = data_filename or f"{self.entity}.json"
        self.state_filename = state_filename or f"{self.entity}_sync_state.json"
        self.state = self._load_state()
        self.data = self._load_data()

    def _ensure_dir(self, filepath: str):
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _load_state(self) -> dict:
        if os.path.exists(self.state_filename):
            with open(self.state_filename, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"last_page": 0, "last_sync": None}

    def _save_state(self):
        self._ensure_dir(self.state_filename)
        with open(self.state_filename, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _load_data(self) -> list:
        if os.path.exists(self.data_filename):
            with open(self.data_filename, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_data(self):
        self._ensure_dir(self.data_filename)
        with open(self.data_filename, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def fetch_page(self, page: int) -> list:
        params = self.params_template.copy()
        params[self.page_param] = page
        params[self.page_size_param] = self.page_size
        response = requests.get(
            self.api_url,
            headers=self.auth_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        # assume payload may wrap items under "itens" or be a list
        if isinstance(payload, dict) and "itens" in payload:
            return payload.get("itens", [])
        if isinstance(payload, list):
            return payload
        # fallback: try first element
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0].get("itens", [])
        return []

    def run_sync(self):
        """Executa ou retoma a sincronização completa da entidade."""
        page = self.state.get("last_page", 0) + 1
        while True:
            items = self.fetch_page(page)
            if not items:
                print(f"[{self.entity}] Sincronização finalizada. Nenhum item na página {page}.")
                break

            self.data.extend(items)
            self.state["last_page"] = page
            self.state["last_sync"] = datetime.utcnow().isoformat() + "Z"
            self._save_data()
            self._save_state()

            print(f"[{self.entity}] Página {page} sincronizada: {len(items)} itens.")
            if len(items) < self.page_size:
                print(f"[{self.entity}] Última página detectada ({page}).")
                break
            page += 1

# Exemplos de uso:
# from app.services.conta_azul_services import get_auth_headers_conta_azul
#
# # Para pessoas:
# sync_pessoas = SyncManager(
#     entity_name="pessoas",
#     api_url="https://api-v2.contaazul.com/v1/pessoa",
#     auth_headers_func=get_auth_headers_conta_azul,
#     params_template={"tipo_perfil": "CLIENTE", "status": "ATIVO"},
#     page_size=10
# )
# sync_pessoas.run_sync()
#
# # Para serviços:
# sync_servicos = SyncManager(
#     entity_name="servicos",
#     api_url="https://api-v2.contaazul.com/v1/servicos",
#     auth_headers_func=get_auth_headers_conta_azul,
#     params_template={"busca_textual": ""},
#     page_size=10
# )
# sync_servicos.run_sync()
