# app/worker/ticket_flow_worker
import time
import logging
import json
from flask import current_app
from app.services.renewal_services import (
    get_waiting_ticket_queue,
    start_ticket_queue,
    update_retry_count_ticket_queue,
)
from app.routes.webhook_routes import (
    envia_comunicado_para_cliente_certif_digital_digisac,
    resposta_certificado_digisac,
    cobranca_gerada,
    envio_cobranca,
    envia_form_agendamento_digisac,
)
from app.utils.utils import debug

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 15  # segundos


# Map nome (str no DB)->função
# (serve para na hora de desempacotar a str do DB, relacionar ao callable no python)
ROUTE_REGISTRY = {
    "envia_comunicado_para_cliente_certif_digital_digisac": envia_comunicado_para_cliente_certif_digital_digisac,
    "resposta_certificado_digisac": resposta_certificado_digisac,
    "cobranca_gerada": cobranca_gerada,
    "envio_cobranca": envio_cobranca,
    "envia_form_agendamento_digisac": envia_form_agendamento_digisac,
}


@debug
def process_queue_item(row: dict):
    queue_id = row["id"]
    func_name = row["func_name"]
    args_json = row["func_args"]

    handler = ROUTE_REGISTRY.get(func_name)
    if not handler:
        logger.error("Rota %s não registrada no ROUTE_REGISTRY", func_name)
        update_retry_count_ticket_queue(queue_id)
        return

    params = json.loads(args_json)
    args = params.get("args", {})
    form = params.get("form", {})
    try:
        # chama o handler **direto**, passando os params como query_string
        # (ele vai ler request.args internamente via test_request_context)
        # mas você pode simular chamando handler(**{}) se extrair tudo por código
        with current_app.test_request_context(
            path="/",  # ou simplesmente '/', query_string=params
            method="POST",
            query_string=args,
            data=form,
        ):
            handler()
        start_ticket_queue(queue_id)
        logger.info("Worker: fila %s processada com sucesso", queue_id)
    except Exception as e:
        logger.error("Worker: erro processando fila %s: %s", queue_id, e)
        update_retry_count_ticket_queue(queue_id)


@debug
def run_ticket_flow_worker():
    while True:
        rows = get_waiting_ticket_queue()
        for row in rows:
            process_queue_item(row)
        time.sleep(CHECK_INTERVAL)
