# app/services/sync/base.py

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional
import requests
from requests import Session, Response

from app.config import Config

logger = logging.getLogger(__name__)


class BaseSyncManager:
    """
    Base para sync paginado de API REST:
    - Reuso de Session
    - Retry simples
    - Timeout padrão
    - Paginação genérica
    - Persistência de JSON
    """

    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2  # segundos

    def __init__(
        self,
        entity: str,
        endpoint: str,
        headers_func: callable,
        params_template: Dict[str, Any],
        page_param: str,
        page_size_param: str,
        page_size: int,
        data_relpath: str,
        state_relpath: Optional[str] = None,
        list_key: str = "itens",
    ):
        self.entity = entity
        self.url = endpoint
        self.get_headers = headers_func
        self.params_template = params_template.copy()
        self.page_param = page_param
        self.page_size_param = page_size_param
        self.page_size = page_size
        self.list_key = list_key

        # Paths absolutos
        self.data_path = os.path.join(Config.SYNC_DATA_DIR, data_relpath)
        self.state_path = (
            os.path.join(Config.SYNC_DATA_DIR, state_relpath) if state_relpath else None
        )

        # Garante diretórios
        for p in filter(None, (self.data_path, self.state_path)):
            d = os.path.dirname(p)
            os.makedirs(d, exist_ok=True)

        # Estado opcional
        self.state = self._load_state() if self.state_path else {"last_page": 0}

        # Dados em memória
        self.data: List[Any] = []

        # Session única
        self.session: Session = requests.Session()

    def _load_state(self) -> Dict[str, Any]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_page": 0}

    def _save_state(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _save_data(self):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[{self.entity}] salvou {len(self.data)} itens em {self.data_path}"
        )

    def _request_with_retry(self, params: Dict[str, Any]) -> Response:
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    self.url,
                    headers=self.get_headers(),
                    params=params,
                    timeout=self.DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"[{self.entity}] tentativa {attempt}/{self.MAX_RETRIES} falhou: {e}"
                )
                time.sleep(self.RETRY_BACKOFF)
        logger.error(f"[{self.entity}] todas tentativas falharam: {last_exc}")
        raise last_exc

    def fetch_page(self, page: int) -> List[Any]:
        params = self.params_template.copy()
        params[self.page_param] = page
        params[self.page_size_param] = self.page_size

        resp = self._request_with_retry(params)
        try:
            payload = resp.json()
        except ValueError as e:
            logger.error(f"[{self.entity}] JSON inválido na página {page}: {e}")
            return []

        # extrai lista
        if isinstance(payload, dict) and self.list_key in payload:
            return payload[self.list_key]
        if isinstance(payload, list):
            return payload
        logger.warning(f"[{self.entity}] payload inesperado: {type(payload)}")
        return []

    def run_sync(self):
        logger.info(f"[{self.entity}] iniciando sync paginado")
        page = self.state.get("last_page", 0) + 1
        while True:
            batch = self.fetch_page(page)
            if not batch:
                logger.info(f"[{self.entity}] fim do sync (página {page} vazia)")
                break
            self.data.extend(batch)
            if self.state_path:
                self.state["last_page"] = page
                self._save_state()
            page += 1
            if len(batch) < self.page_size:
                logger.info(f"[{self.entity}] última página detectada ({page-1})")
                break

        self._save_data()
        logger.info(f"[{self.entity}] sincronização concluída")
