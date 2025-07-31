# app/services/sync/digisac_sync_manager.py
import os
from app.services.sync.base import BaseSyncManager
from app.services.digisac.digisac_services import get_auth_headers_digisac

# Relpaths dentro de app/database/digisac/
CONTACT_PATH = os.path.join("digisac", "contacts.json")
DEPT_PATH = os.path.join("digisac", "departments.json")
USER_PATH = os.path.join("digisac", "users.json")

CONTACT_STATE = os.path.join("digisac", "contacts_state.json")
DEPT_STATE = os.path.join("digisac", "departments_state.json")
USER_STATE = os.path.join("digisac", "users_state.json")


class ContactsSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 40):
        super().__init__(
            entity="DS::Contacts",
            endpoint="https://logicassessoria.digisac.chat/api/v1/contacts",
            headers_func=get_auth_headers_digisac,
            params_template={},  # perPage/page
            page_param="page",
            page_size_param="perPage",
            page_size=page_size,
            data_relpath=CONTACT_PATH,
            state_relpath=CONTACT_STATE,
            list_key="data",
        )


class DepartmentsSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 40):
        super().__init__(
            entity="DS::Departments",
            endpoint="https://logicassessoria.digisac.chat/api/v1/departments",
            headers_func=get_auth_headers_digisac,
            params_template={},
            page_param="page",
            page_size_param="perPage",
            page_size=page_size,
            data_relpath=DEPT_PATH,
            state_relpath=DEPT_STATE,
            list_key="data",
        )


class UsersSyncManager(BaseSyncManager):
    def __init__(self, page_size: int = 40):
        super().__init__(
            entity="DS::Users",
            endpoint="https://logicassessoria.digisac.chat/api/v1/users",
            headers_func=get_auth_headers_digisac,
            params_template={},
            page_param="page",
            page_size_param="perPage",
            page_size=page_size,
            data_relpath=USER_PATH,
            state_relpath=USER_STATE,
            list_key="data",
        )
