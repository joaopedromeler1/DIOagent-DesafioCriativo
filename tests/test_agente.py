import json
from datetime import timedelta
from types import SimpleNamespace

import anthropic
import httpx

from agente import agente as mod_agente
from agente.agente import MSG_INSTABILIDADE, contar_linhas, conteudo_para_historico

from .conftest import texto, usa_ferramenta


def nova_sessao(s, tel="5511900000001"):
    return s.sessoes.obter(tel, "Fulano", s.relogio())


def test_loop_de_ferramenta_e_historico_consistente(sistema):
    agente, cliente = sistema.agente([usa_ferramenta("listar_procedimentos", {}), texto("A limpeza custa R$ 200,00; a reserva é de R$ 60,00.")])
    sessao = nova_sessao(sistema)
    resp = agente.responder(sessao, "Quanto custa a limpeza?")
    assert "R$ 200,00" in resp
    papeis = [m["role"] for m in sessao.mensagens]
    assert papeis == ["user", "assistant", "user", "assistant"]
    resultado = sessao.mensagens[2]["content"][0]
    assert resultado["type"] == "tool_result" and resultado["tool_use_id"] == "tu_1" and not resultado["is_error"]
    assert "R$ 60,00" in resultado["content"]
    # a chamada leva o prompt oficial + contexto e as ferramentas
    kw = cliente.chamadas[0]
    assert "Agente de Atendimento Odontológico" in kw["system"][0]["text"]
    assert "Data e hora atuais" in kw["system"][1]["text"]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"


def test_varias_ferramentas_em_uma_mensagem(sistema):
    dupla = SimpleNamespace(
        stop_reason="tool_use",
        content=[
            SimpleNamespace(type="tool_use", id="a", name="listar_procedimentos", input={}),
            SimpleNamespace(type="tool_use", id="b", name="informacoes_clinica", input={}),
        ],
    )
    agente, _ = sistema.agente([dupla, texto("Ok.")])
    sessao = nova_sessao(sistema)
    agente.responder(sessao, "oi")
    assert [r["tool_use_id"] for r in sessao.mensagens[2]["content"]] == ["a", "b"]


def test_resposta_longa_e_reescrita_em_4_linhas(sistema):
    longa = "\n".join(f"linha {i}" for i in range(6))
    agente, cliente = sistema.agente([texto(longa), texto("Resposta curta.\nSegunda linha.")])
    sessao = nova_sessao(sistema)
    resp = agente.responder(sessao, "oi")
    assert contar_linhas(resp) <= 4
    assert cliente.chamadas[1]["tool_choice"] == {"type": "none"}
    assert sessao.mensagens[-1]["role"] == "assistant"  # histórico só cresce


def test_conversa_acima_de_30_min_encaminha_sem_chamar_modelo(sistema):
    agente, cliente = sistema.agente([])
    sessao = nova_sessao(sistema)
    sessao.registro.append("Reserva R1 aguardando pagamento")
    sistema.relogio.t += timedelta(minutes=31)
    resp = agente.responder(sessao, "ainda aí?")
    assert cliente.chamadas == [] and sessao.encaminhado
    assert "Reserva R1" in resp and "atendente" in resp and contar_linhas(resp) <= 4
    assert agente.responder(sessao, "alô") is None  # depois do encaminhamento o agente se cala
    linhas = (sistema.tmp / "enc.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(linhas[0])["motivo"].startswith("Conversa acima de 30")


def test_ferramenta_de_encaminhamento_silencia_o_agente(sistema):
    agente, _ = sistema.agente([
        usa_ferramenta("encaminhar_para_humano", {"motivo": "Quer falar com o dentista", "resumo": "Nome: Fulano"}),
        texto("Vou encaminhá-lo a um atendente, pois deseja falar com o dentista. Já registrei seu nome."),
    ])
    sessao = nova_sessao(sistema)
    assert "atendente" in agente.responder(sessao, "Quero falar com a doutora")
    assert sessao.encaminhado and agente.responder(sessao, "oi") is None


def test_erro_de_api_devolve_mensagem_e_nao_suja_historico(sistema):
    erro = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    agente, _ = sistema.agente([erro])
    sessao = nova_sessao(sistema)
    assert agente.responder(sessao, "oi") == MSG_INSTABILIDADE
    assert sessao.mensagens == []


def test_recusa_do_modelo_encaminha_para_humano(sistema):
    agente, _ = sistema.agente([SimpleNamespace(stop_reason="refusal", content=[])])
    sessao = nova_sessao(sistema)
    assert "atendente" in agente.responder(sessao, "...")
    assert sessao.encaminhado


def test_eco_apos_fallback_remove_blocos_anteriores():
    b = lambda t: SimpleNamespace(type=t)
    conteudo = [b("thinking"), b("tool_use"), b("text"), b("fallback"), b("thinking"), b("text")]
    tipos = [x.type for x in conteudo_para_historico(conteudo)]
    assert tipos == ["text", "fallback", "thinking", "text"]


def test_conversa_inativa_inicia_nova_sessao(sistema):
    s1 = nova_sessao(sistema)
    sistema.relogio.t += timedelta(minutes=121)
    s2 = nova_sessao(sistema)
    assert s1 is not s2
