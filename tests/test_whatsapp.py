import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from agente import whatsapp

from .conftest import texto, usa_ferramenta


@pytest.fixture
def api(sistema, monkeypatch):
    enviados = []
    agente, _ = sistema.agente([texto("Olá! Como posso ajudar?")])
    monkeypatch.setattr(whatsapp, "_sistema", (agente, sistema.sessoes, sistema.agenda))
    monkeypatch.setattr(whatsapp, "enviar_whatsapp", lambda tel, msg: enviados.append((tel, msg)))
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "tok")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "segredo")
    monkeypatch.setenv("PAGAMENTO_WEBHOOK_SECRET", "pg")
    whatsapp._vistas.clear()
    return TestClient(whatsapp.app), enviados


def corpo(texto_msg="Oi", id="wamid.1", tipo="text"):
    msg = {"from": "5511900000001", "id": id, "type": tipo}
    if tipo == "text":
        msg["text"] = {"body": texto_msg}
    return json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "5511900000001", "profile": {"name": "Fulano"}}], "messages": [msg]}}]}]}).encode()


def assinar(b):
    return "sha256=" + hmac.new(b"segredo", b, hashlib.sha256).hexdigest()


def test_verificacao_do_webhook(api):
    c, _ = api
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "123"}).text == "123"
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "1"}).status_code == 403


def test_mensagem_assinada_gera_resposta(api):
    c, enviados = api
    b = corpo()
    assert c.post("/webhook", content=b, headers={"X-Hub-Signature-256": assinar(b)}).status_code == 200
    assert enviados == [("5511900000001", "Olá! Como posso ajudar?")]


def test_assinatura_invalida_e_rejeitada(api):
    c, enviados = api
    assert c.post("/webhook", content=corpo(), headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 403
    assert enviados == []


def test_mensagem_repetida_pela_meta_e_ignorada(api):
    c, enviados = api
    b = corpo()
    for _ in range(2):
        c.post("/webhook", content=b, headers={"X-Hub-Signature-256": assinar(b)})
    assert len(enviados) == 1


def test_mensagem_nao_textual(api):
    c, enviados = api
    b = corpo(tipo="audio", id="wamid.2")
    c.post("/webhook", content=b, headers={"X-Hub-Signature-256": assinar(b)})
    assert "apenas mensagens de texto" in enviados[0][1]


def test_webhook_de_pagamento_confirma_e_avisa(api, sistema):
    c, enviados = api
    r = sistema.agenda.criar_reserva_pendente("5511900000001", "A", "consulta_avaliacao", "dra_ana", __import__("datetime").datetime(2026, 11, 12, 10, 0))
    assert c.post("/pagamentos/webhook", json={"reserva_id": r.id}, headers={"X-Webhook-Secret": "errado"}).status_code == 403
    resp = c.post("/pagamentos/webhook", json={"reserva_id": r.id}, headers={"X-Webhook-Secret": "pg"})
    assert resp.json()["status"] == "confirmada"
    assert "Pagamento confirmado" in enviados[0][1]
