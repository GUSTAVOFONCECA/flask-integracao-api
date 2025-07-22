# app/worker/ticket_flow_worker
import time
import logging
from app.services.webhook_services import has_open_ticket_for_user
from app.services.renewal_services import (
    get_waiting_ticket_queue,
    get_pending,
    add_pending,
    start_ticket_queue,
    update_retry_count_ticket_queue,
    update_last_checked_ticket_queue,
)

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # segundos


def run_ticket_flow_worker() -> None:
    while True:
        rows = get_waiting_ticket_queue()

        for row in rows:
            queue_id = row["id"]
            spa_id = row["spa_id"]
            contact = row["contact_number"]

            logger.info("Verificando ticket aberto para SPA %s", spa_id)
            if not has_open_ticket_for_user(contact):
                try:
                    pending = get_pending(spa_id=spa_id)
                    add_pending(
                        company_name=pending.get("company_name"),
                        contact_number=contact,
                        contact_name=pending.get("contact_name"),
                        deal_type=pending.get("deal_type"),
                        spa_id=spa_id,
                        status='pending'
                    )
                    # Atualiza status para started
                    start_ticket_queue(queue_id)
                except Exception as e:
                    logger.error("Erro ao inciar fluxo para SPA %s: %s", spa_id, e)
                    update_retry_count_ticket_queue(queue_id)
            else:
                update_last_checked_ticket_queue(queue_id)
        time.sleep(CHECK_INTERVAL)
