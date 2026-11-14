"""Servidor de webhooks: WhatsApp Cloud API (Meta) + aviso de pagamento.

    uvicorn agente.whatsapp:app --port 8000

Variáveis de ambiente:
  WHATSAPP_VERIFY_TOKEN   token escolhido por você ao cadastrar o webhook na Meta
  WHATSAPP_APP_SECRET     segredo do app (valida a assinatura X-Hub-Signature-256)
  WHATSAPP_TOKEN          token de acesso para enviar mensagens
  WHATSAPP_PHONE_ID       ID do número de telefone da API
  PAGAMENTO_WEBHOOK_SECRET segredo que o gateway envia no header X-Webhook-Secret
"""
import hashlib
import hmac
import logging
import os
from collections import OrderedDict

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response

from . import config
from .agenda import CONFIRMADA, legivel
from .fabrica import criar_sistema

log = logging.getLogger(__name__)
GRAPH_URL = "https://graph.facebook.com/v21.0"
MSG_SO_TEXTO = "No momento consigo atender apenas mensagens de texto. Poderia escrever sua dúvida?"

app = FastAPI(title="Agente odontológico - WhatsApp")
_sistema = None
_vistas: OrderedDict[str, None] = OrderedDict()  # ids de mensagens já tratadas (a Meta reenvia)


def sistema():
    global _sistema
    if _sistema is None:
        _sistema = criar_sistema(demo=os.getenv("AGENTE_DEMO") == "1")
    return _sistema


def enviar_whatsapp(telefone: str, texto: str) -> None:
    token, phone_id = os.getenv("WHATSAPP_TOKEN"), os.getenv("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        log.error("WHATSAPP_TOKEN/WHATSAPP_PHONE_ID não configurados; mensagem não enviada.")
        return
    r = httpx.post(
        f"{GRAPH_URL}/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "to": telefone, "type": "text", "text": {"body": texto}},
        timeout=15,
    )
    if r.status_code >= 400:
        log.error("Falha ao enviar WhatsApp (%s): %s", r.status_code, r.text)


def _assinatura_valida(corpo: bytes, assinatura: str | None) -> bool:
    segredo = os.getenv("WHATSAPP_APP_SECRET")
    if not segredo:
        log.warning("WHATSAPP_APP_SECRET ausente: assinatura NÃO validada (use apenas em testes).")
        return True
    esperado = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura or "")


def atender(telefone: str, nome: str | None, texto: str | None) -> None:
    agente, sessoes, _ = sistema()
    sessao = sessoes.obter(telefone, nome, config.agora())
    resposta = MSG_SO_TEXTO if texto is None else agente.responder(sessao, texto)
    if resposta:
        enviar_whatsapp(telefone, resposta)


@app.get("/webhook")
def verificar(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN") and os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return Response(q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "token inválido")


@app.post("/webhook")
async def receber(request: Request, tarefas: BackgroundTasks, x_hub_signature_256: str | None = Header(default=None)):
    corpo = await request.body()
    if not _assinatura_valida(corpo, x_hub_signature_256):
        raise HTTPException(403, "assinatura inválida")
    dados = await request.json()
    for entrada in dados.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            nomes = {c.get("wa_id"): c.get("profile", {}).get("name") for c in valor.get("contacts", [])}
            for msg in valor.get("messages", []):
                if msg["id"] in _vistas:
                    continue
                _vistas[msg["id"]] = None
                while len(_vistas) > 2000:
                    _vistas.popitem(last=False)
                texto = msg["text"]["body"] if msg.get("type") == "text" else None
                tarefas.add_task(atender, msg["from"], nomes.get(msg["from"]), texto)
    return {"status": "ok"}  # a Meta exige resposta rápida


@app.post("/pagamentos/webhook")
async def pagamento(request: Request, tarefas: BackgroundTasks, x_webhook_secret: str | None = Header(default=None)):
    segredo = os.getenv("PAGAMENTO_WEBHOOK_SECRET")
    if not segredo or not hmac.compare_digest(segredo, x_webhook_secret or ""):
        raise HTTPException(403, "segredo inválido")
    reserva_id = (await request.json()).get("reserva_id")
    _, _, agenda = sistema()
    try:
        reserva = agenda.confirmar_pagamento(reserva_id)
    except KeyError:
        raise HTTPException(404, "reserva não encontrada")
    if reserva.status == CONFIRMADA:  # mensagem fixa, gerada pelo sistema, não pelo modelo
        tarefas.add_task(
            enviar_whatsapp,
            reserva.telefone,
            f"Pagamento confirmado! Seu agendamento está garantido para {legivel(reserva.inicio)}.",
        )
    return {"reserva_id": reserva.id, "status": reserva.status}
