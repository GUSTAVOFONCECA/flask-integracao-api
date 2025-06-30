# app/tasks.py
import threading
import time
import logging
import requests
from app.database.database import get_db_connection
from app.services.conta_azul.conta_azul_services import get_sale_pdf
from app.services.webhook_services import build_billing_certification_pdf
from app.services.renewal_services import complete_pending

logger = logging.getLogger(__name__)


def pdf_sender_worker():
    while True:
        try:
            with get_db_connection() as conn:
                # Busca pendências com billing criado mas PDF não enviado
                pending = conn.execute(
                    "SELECT * FROM certif_pending_renewals WHERE status = 'billing_created'"
                ).fetchall()

                for row in pending:
                    task = dict(row)
                    try:
                        # Baixa o PDF diretamente da URL
                        response = requests.get(
                            task["pdf_url"], timeout=30
                        )
                        response.raise_for_status()

                        pdf_content = response.content
                        filename = f"boleto-{task['billing_id'][:8]}.pdf"

                        # Envia via Digisac
                        build_billing_certification_pdf(
                            contact_number=task["contact_number"],
                            pdf_content=pdf_content,
                            filename=filename,
                        )

                        # Atualiza status para concluído
                        conn.execute(
                            "UPDATE certif_pending_renewals SET status = 'completed' WHERE id = ?",
                            (task["id"],),
                        )
                        conn.commit()

                    except Exception as e:
                        logger.error(f"Erro ao enviar PDF: {str(e)}")
                        conn.execute(
                            "UPDATE certif_pending_renewals SET retry_count = COALESCE(retry_count, 0) + 1 WHERE id = ?",
                            (task["id"],),
                        )
                        conn.commit()

            time.sleep(30)
        except Exception as e:
            logger.exception(f"Erro no worker: {str(e)}")
            time.sleep(60)


# Inicia o worker quando o app iniciar
def start_workers():
    if not hasattr(start_workers, "worker_started"):
        thread = threading.Thread(target=pdf_sender_worker, daemon=True)
        thread.start()
        start_workers.worker_started = True
