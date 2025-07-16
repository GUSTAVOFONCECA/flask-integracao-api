# app/routes/webhook_routes.py

"""
Rotas de webhook para integração com Bitrix24 e validação de CNPJ.
"""

from datetime import datetime
import logging
import json
from flask import Blueprint, request, jsonify

from app.services.webhook_services import (
    get_cnpj_receita,
    update_company_process_cnpj,
    post_destination_api,
    verify_webhook_signature,
    update_crm_item,
    update_deal_item,
    _get_contact_id_by_number,
    _get_contact_number_by_id,
    add_comment_crm_timeline,
)

# Importar wrappers do fluxo de Certificação Digital
from app.services.webhook_services import (
    interpret_certification_response,
    send_proposal_file,
    build_transfer_to_certification,
    build_certification_message,
    build_form_agendamento,
    build_billing_certification_pdf,
)

from app.services.conta_azul.conta_azul_services import (
    handle_sale_creation_certif_digital,
    extract_billing_info,
)

from app.services.renewal_services import (
    add_pending,
    get_pending,
    update_pending,
    is_message_processed,
    check_pending_status,
    mark_message_processed,
    compute_hash,
    complete_pending,
)

from app.utils.utils import respond_with_200_on_exception

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)


@webhook_bp.route("/consulta-receita", methods=["POST"])
def valida_cnpj_receita_bitrix():
    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403

    required_params = ["idEmpresa", "CNPJ"]
    missing = [p for p in required_params if not request.args.get(p)]
    if missing:
        return (
            jsonify(
                {"error": f"Parâmetros obrigatórios faltando: {', '.join(missing)}"}
            ),
            400,
        )

    id_empresa = request.args["idEmpresa"]
    cnpj = request.args["CNPJ"]
    raw = get_cnpj_receita(cnpj)
    if not raw:
        return jsonify({"error": "Dados do CNPJ não encontrados"}), 502

    processed = update_company_process_cnpj(raw, id_empresa)
    api_url = (
        "https://logic.bitrix24.com.br/rest/260/af4o31dew3vzuphs/crm.company.update"
    )
    response = post_destination_api(processed, api_url)
    return jsonify({"status": "received", "response": response}), 200


@webhook_bp.route("/aviso-certificado", methods=["POST"])
@respond_with_200_on_exception
def envia_comunicado_para_cliente_certif_digital_digisac():
    logger.info("/aviso-certificado recebido, criando pendência")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    # Valida assinatura
    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        logger.warning("Assinatura inválida recebida em /certificacao-digital.")
        return jsonify({"error": "Assinatura inválida"}), 403

    contact_number = request.args.get("contactNumber")
    company_name = request.args.get("companyName")
    contact_name = request.args.get("contactName")
    days_to_expire_str = request.args.get("daysToExpire")
    spa_id_str = request.args.get("idSPA")
    deal_type = request.args.get("dealType")

    if not all(
        [
            contact_number,
            company_name,
            contact_name,
            days_to_expire_str,
            spa_id_str,
            deal_type,
        ]
    ):
        logger.error("Missing required parameters in /certificacao-digital.")
        return (
            jsonify(
                {
                    "error": "Parâmetros contactNumber, contact_name, "
                    "companyName, daysToExpire, idSPA e dealType são obrigatórios"
                }
            ),
            400,
        )

    try:
        days_to_expire = int(days_to_expire_str)
        spa_id = int(spa_id_str)
    except ValueError:
        logger.error(
            f"Invalid daysToExpire ({days_to_expire_str}) or idSPA ({spa_id_str}). Must be integers."
        )
        return (
            jsonify({"error": "daysToExpire e idSPA devem ser números inteiros"}),
            400,
        )

    event_type = "pending"

    # Gerar um message_id robusto para deduplicação EXATA do webhook.
    # Se o webhook já fornecesse um ID transacional para esta ação, usaríamos.
    # Como não temos, usamos um hash do payload, incluindo o spa_id e os dias para expirar,
    # pois a mesma mensagem para o mesmo SPA com os mesmos dias deve ser considerada duplicada.
    webhook_message_id = compute_hash(
        {
            "spa_id": spa_id,
            "event_type": event_type,
            "company_name": company_name,
            "contact_name": contact_name,
            "days_to_expire": days_to_expire,  # Importante para saber se é o mesmo aviso
        }
    )

    # 1. Deduplicação de Webhook Exato: Verificar se este webhook específico já foi processado.
    if is_message_processed(webhook_message_id):
        logger.info(
            f"Evento duplicado EXATO (ID: {webhook_message_id}, Tipo: {event_type}) para SPA ID {spa_id}. Ignorando."
        )
        return (
            jsonify(
                {
                    "status": "ignored",
                    "message": "Webhook de aviso de vencimento já processado anteriormente.",
                }
            ),
            200,
        )

    # 2. Controle de Fluxo de Negócio: Verificar o status atual
    # do SPA ID para evitar comandos redundantes semanticamente.
    current_pending_status = check_pending_status(spa_id)

    # Se o SPA já está em um estágio avançado, talvez não precise enviar o aviso novamente.
    # Ajuste esta lógica conforme seu fluxo de negócio.
    # Ex: Se já enviou proposta ou está agendando, não envia o aviso inicial.
    if current_pending_status in [
        "renewal_proposal_sent",
        "scheduling_form_sent",
        "billing_processed",
        "billing_pdf_sent",
        "complete",
        "recused",
    ]:
        logger.info(
            f"Aviso de vencimento para SPA ID {spa_id} ignorado. Status atual: "
            f"'{current_pending_status}'. Comando semântico duplicado/desnecessário para o estado atual do negócio."
        )
        # Registrar que o comando foi recebido mas não executado devido ao estado do negócio
        mark_message_processed(
            spa_id, webhook_message_id, event_type, request.args.to_dict()
        )
        return (
            jsonify(
                {
                    "status": "ignored",
                    "message": (
                        "Comando de aviso de vencimento desnecessário "
                        "para o estado atual do negócio.",
                    ),
                }
            ),
            200,
        )

    # Adiciona ou atualiza a pendência no banco de dados.
    # Se não existe, cria. Se existe, atualiza os dados mas mantém o status.
    add_pending(company_name, contact_number, deal_type, spa_id)

    # Abre chamado e envia a mensagem de aviso de vencimento.
    build_transfer_to_certification(contact_number)
    build_certification_message(
        contact_number, contact_name, company_name, days_to_expire
    )

    # Registra comentário no CRM
    add_comment_crm_timeline(
        {
            "ENTITY_ID": spa_id,
            "ENTITY_TYPE": "DYNAMIC_137",
            "COMMENT": f"Enviado aviso em {datetime.now():%Y-%m-%d %H:%M}",
        }
    )

    # Atualiza o status da pendência APÓS a ação ser bem-sucedida.
    update_pending(spa_id, event_type)  # Atualiza para 'initial_info_sent'
    logger.info(
        f"Status da pendência para SPA ID {spa_id} atualizado para '{event_type}'."
    )

    # Registrar o processamento da mensagem.
    mark_message_processed(
        spa_id, webhook_message_id, event_type, request.args.to_dict()
    )
    logger.info(
        f"Evento {event_type} para SPA ID {spa_id} processado e registrado com ID {webhook_message_id}."
    )

    return (
        jsonify(
            {
                "status": "success",
                "message": "Mensagem de certificação digital enviada com sucesso",
            }
        ),
        200,
    )


@webhook_bp.route("/digisac", methods=["POST"])
@respond_with_200_on_exception
def resposta_certificado_digisac():
    """
    Processa respostas de clientes vindas do Digisac.
    Implementa deduplicação de mensagens e uma máquina de estados para
    garantir que cada etapa do processo de renovação ocorra apenas uma vez.
    """
    logger.info("/digisac: Webhook recebido")
    request_json = request.get_json(silent=True)
    if not request_json:
        logger.warning("/digisac: Requisição sem payload JSON.")
        return jsonify({"error": "Payload JSON ausente"}), 400

    logger.debug(f"/digisac: Payload: {json.dumps(request_json)}")

    # 1. Extrair IDs essenciais e a mensagem do usuário
    msg = request_json.get("data", {}).get("message", {})
    message_id = msg.get("id") or msg.get("messageId")
    contact_id = request_json.get("data", {}).get("contactId")
    user_message = msg.get("text", "")

    if not message_id or not contact_id:
        logger.warning("/digisac: 'message_id' ou 'contactId' ausente no payload.")
        return jsonify({"error": "'message_id' e 'contactId' são obrigatórios"}), 400

    # 2. Obter a pendência de renovação (a mais recente e ativa para o contato)
    contact_number = _get_contact_number_by_id(contact_id=contact_id)
    if not contact_number:
        logger.error(
            f"/digisac: Contato não encontrado no cache local (ID: {contact_id})."
        )
        return (
            jsonify({"status": "ignored", "reason": "Número do contato desconhecido"}),
            200,
        )

    pending = get_pending(contact_number=contact_number)
    if not pending:
        logger.warning(
            f"/digisac: Nenhuma solicitação de renovação ativa para o contato {contact_number}."
        )
        return (
            jsonify(
                {
                    "status": "ignored",
                    "reason": "Nenhuma solicitação pendente encontrada",
                }
            ),
            200,
        )

    spa_id = pending.get("spa_id")
    current_status = pending.get("status")
    logger.info(
        f"Processando resposta para SPA ID: {spa_id} (Status Atual: '{current_status}')"
    )

    # 3. Camada 1: Deduplicação de Mensagem
    # Se esta mensagem específica já foi processada, ignore-a completamente.
    if is_message_processed(message_id):
        logger.info(
            f"Mensagem duplicada (ID: {message_id}) para SPA ID {spa_id}. Ignorando."
        )
        return jsonify({"status": "duplicate_message", "message_id": message_id}), 200

    # 4. Interpretar a intenção do usuário
    response_type = interpret_certification_response(user_message)
    logger.info(
        f"Intenção interpretada como '{response_type}' para a mensagem: '{user_message}'"
    )

    action_performed = False
    try:
        # 5. Camada 2: Máquina de Estados (lógica de negócio)
        if response_type == "renew":
            # Só cria a venda se o processo estiver em um estágio inicial.
            if current_status in ["pending", "info_sent"]:
                logger.info(
                    f"[SPA ID: {spa_id}] Cliente solicitou RENOVAÇÃO. Iniciando processo de venda."
                )
                send_proposal_file(
                    pending.get("contact_number"), pending.get("company_name"), spa_id
                )
                result = handle_sale_creation_certif_digital(
                    pending.get("contact_number"), pending.get("deal_type")
                )
                sale_id = result.get("sale", {}).get("id")

                update_pending(spa_id, status="sale_created", sale_id=sale_id)
                update_crm_item(
                    entity_type_id=137,
                    spa_id=spa_id,
                    fields={"stageId": "DT137_36:UC_90X241"},
                )
                action_performed = True
                logger.info(
                    f"[SPA ID: {spa_id}] Venda criada (ID: {sale_id}). Status: 'sale_created'."
                )
            else:
                logger.warning(
                    f"[SPA ID: {spa_id}] Solicitação de RENOVAÇÃO ignorada. Status '{current_status}' não permite esta ação."
                )

        elif response_type == "info":
            # Só envia informações se a venda ainda não foi criada.
            if current_status == "pending":
                logger.info(
                    f"[SPA ID: {spa_id}] Cliente solicitou INFO. Enviando proposta."
                )
                send_proposal_file(
                    pending.get("contact_number"), pending.get("company_name"), spa_id
                )
                update_pending(spa_id, status="info_sent")
                action_performed = True
                logger.info(
                    f"[SPA ID: {spa_id}] Proposta enviada. Status: 'info_sent'."
                )
            else:
                logger.warning(
                    f"[SPA ID: {spa_id}] Solicitação de INFO ignorada. Status '{current_status}' não permite esta ação."
                )

        elif response_type == "refuse":
            # O cliente pode recusar a qualquer momento antes da conclusão.
            if current_status != "customer_retention":
                logger.info(
                    f"[SPA ID: {spa_id}] Cliente RECUSOU. Movendo para retenção."
                )
                update_crm_item(
                    entity_type_id=137,
                    spa_id=spa_id,
                    fields={"stageId": "DT137_36:UC_AY5334"},
                )
                update_pending(spa_id, status="customer_retention")
                action_performed = True
                logger.info(
                    f"[SPA ID: {spa_id}] Card movido para retenção. Status: 'customer_retention'."
                )
            else:
                logger.warning(
                    f"[SPA ID: {spa_id}] Solicitação de RECUSA ignorada. Já está em retenção."
                )

        else:  # "unknown"
            logger.info(
                f"[SPA ID: {spa_id}] Resposta não reconhecida: '{user_message}'. Nenhuma ação de negócio executada."
            )
            # Mesmo não executando uma ação de negócio, marcamos a mensagem para não
            # reprocessar a mesma resposta desconhecida repetidamente.
            action_performed = True

    finally:
        # 6. Registrar que esta mensagem foi processada para evitar repetições.
        # Isso é crucial e é executado mesmo que nenhuma ação de negócio tenha sido tomada.
        mark_message_processed(spa_id, message_id, response_type, request_json)
        logger.info(
            f"Mensagem (ID: {message_id}) marcada como processada para SPA ID {spa_id}."
        )

    return jsonify({"status": "processed", "action_performed": action_performed}), 200


@webhook_bp.route("/cobranca-gerada", methods=["POST"])
@respond_with_200_on_exception
def cobranca_gerada():
    logger.info("/cobranca-gerada recebido — salvando dados de cobrança")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    contact_number = request.args.get("contactNumber") or request.json.get(
        "contactNumber"
    )
    deal_id = request.args.get("dealId")

    if not contact_number:
        return jsonify({"error": "contactNumber ausente"}), 400

    pending = get_pending(contact_number)
    if not pending:
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        info = extract_billing_info(contact_number)
        update_pending(
            spa_id=pending.get("spa_id"),
            status="billing_generated",
            financial_event_id=info["financial_event_id"],
        )

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "UF_CRM_1751478607": info["boleto_url"],
            },
        )

        return (
            jsonify(
                {
                    "status": "billing_generated",
                    "message": "Cobrança identificada e status atualizado",
                    "event_id": info["financial_event_id"],
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao processar cobrança: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/envio-cobranca", methods=["POST"])
@respond_with_200_on_exception
def envio_cobranca():
    logger.info("/envio-cobranca recebido — enviando boleto via Digisac")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    params = request.args or request.get_json(silent=True) or {}
    spa_id = params.get("idSPA")
    deal_id = params.get("idDeal")

    if not deal_id or not spa_id:
        return jsonify({"error": f"idSPA {spa_id} ou idDeal {deal_id} ausentes"}), 400

    pending = get_pending(spa_id=spa_id)
    if not pending or not isinstance(pending, dict):
        return jsonify({"error": "Nenhuma solicitação pendente"}), 404

    try:
        build_billing_certification_pdf(
            contact_number=pending.get("contact_number"),
            company_name=pending.get("company_name"),
            deal_id=deal_id,
            filename=f"Cobrança_certificado_digital_-_{pending.get('company_name', '')}.pdf",
        )

        update_pending(spa_id=pending.get("spa_id"), status="billing_pdf_sent")

        update_deal_item(
            entity_type_id=18,
            deal_id=deal_id,
            fields={
                "STAGE_ID": "C18:PREPARATION",
            },
        )

        return (
            jsonify(
                {
                    "status": "billing_sent",
                    "message": "Boleto enviado com sucesso via Digisac",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Erro ao enviar boleto: %s", e)
        return jsonify({"error": str(e)}), 500


@webhook_bp.route("/agendamento-certificado", methods=["POST"])
@respond_with_200_on_exception
def envia_form_agendamento_digisac() -> dict:
    """Função para envio de formulário para agendamento ao cliente"""
    logger.info(
        "/agendamento-certificado recebido, enviando agendamento de videoconferência"
    )
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Args: {request.args.to_dict()}")
    logger.debug(f"Form: {request.form.to_dict()}")
    logger.debug(f"JSON: {request.get_json(silent=True)}")

    signature = request.form.get("auth[member_id]", "")
    if not verify_webhook_signature(signature):
        return jsonify({"error": "Assinatura inválida"}), 403
    try:
        company_name = request.args.get("companyName")
        contact_number = request.args.get("contactNumber")
        schedule_form_link = request.args.get("linkFormAgendamento")
        spa_id = request.args.get("idSPA")

        build_form_agendamento(contact_number, company_name, schedule_form_link)
        update_pending(spa_id, "scheduling_form_sent")

        return (
            jsonify(
                {
                    "status": "success",
                    "message": """
                    Formulário para agendamento de 
                    videoconferência enviado com sucesso
                    """,
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Erro ao enviar agendamento: %s", str(e))
        return jsonify({"error": str(e)}), 500
