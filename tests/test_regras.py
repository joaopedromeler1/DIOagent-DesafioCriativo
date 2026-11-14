import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from agente import agenda as ag
from agente.conhecimento import brl, calcular_reserva

QUINTA_10H = datetime(2026, 11, 12, 10, 0)


def test_reserva_e_30_por_cento_arredondada():
    assert calcular_reserva(Decimal("150.00")) == Decimal("45.00")
    assert calcular_reserva(Decimal("200.00")) == Decimal("60.00")
    assert calcular_reserva(Decimal("0.05")) == Decimal("0.02")  # 0,015 -> arredonda para cima


def test_formato_brl():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"


def test_horarios_respeitam_agenda_e_passado(sistema):
    hs = sistema.agenda.horarios_livres("limpeza", date(2026, 11, 11), date(2026, 11, 11))
    inicios = [h["inicio"] for h in hs]
    assert "2026-11-11T09:00" not in inicios  # já passou/agora
    assert "2026-11-11T09:30" in inicios
    # limpeza dura 60 min: não pode começar 11:30 (invadiria o almoço)
    todos = sistema.agenda.horarios_livres("limpeza", date(2026, 11, 11), date(2026, 11, 11), limite=100)
    assert "2026-11-11T11:30" not in [h["inicio"] for h in todos]
    assert "2026-11-11T12:00" not in [h["inicio"] for h in todos]


def test_fim_de_semana_sem_horarios(sistema):
    assert sistema.agenda.horarios_livres("limpeza", date(2026, 11, 14), date(2026, 11, 15)) == []


def test_pendente_nao_bloqueia_horario(sistema):
    r = sistema.agenda.criar_reserva_pendente("5511900000001", "Fulano", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    assert r.status == ag.PENDENTE
    livres = [h["inicio"] for h in sistema.agenda.horarios_livres("consulta_avaliacao", date(2026, 11, 12), date(2026, 11, 12), "dra_ana", limite=100)]
    assert "2026-11-12T10:00" in livres


def test_confirmada_so_depois_do_pagamento_e_bloqueia(sistema):
    r = sistema.agenda.criar_reserva_pendente("5511900000001", "Fulano", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    assert sistema.agenda.obter(r.id, "5511900000001").status == ag.PENDENTE
    sistema.agenda.confirmar_pagamento(r.id)
    assert sistema.agenda.obter(r.id, "5511900000001").status == ag.CONFIRMADA
    livres = [h["inicio"] for h in sistema.agenda.horarios_livres("consulta_avaliacao", date(2026, 11, 12), date(2026, 11, 12), "dra_ana", limite=100)]
    assert "2026-11-12T10:00" not in livres
    with pytest.raises(ValueError):
        sistema.agenda.criar_reserva_pendente("5511900000002", "Outro", "consulta_avaliacao", "dra_ana", QUINTA_10H)


def test_pagamento_de_horario_ocupado_vira_conflito(sistema):
    a = sistema.agenda.criar_reserva_pendente("5511900000001", "A", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    b = sistema.agenda.criar_reserva_pendente("5511900000002", "B", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    sistema.agenda.confirmar_pagamento(a.id)
    assert sistema.agenda.confirmar_pagamento(b.id).status == ag.CONFLITO


def test_confirmacao_idempotente(sistema):
    r = sistema.agenda.criar_reserva_pendente("5511900000001", "A", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    sistema.agenda.confirmar_pagamento(r.id)
    assert sistema.agenda.confirmar_pagamento(r.id).status == ag.CONFIRMADA


def test_paciente_nao_ve_reserva_de_outro(sistema):
    r = sistema.agenda.criar_reserva_pendente("5511900000001", "A", "consulta_avaliacao", "dra_ana", QUINTA_10H)
    assert sistema.agenda.obter(r.id, "5511900000002") is None
    assert sistema.agenda.reservas_do_paciente("5511900000002") == []


def test_ferramenta_verificar_pagamento_isolada_por_telefone(sistema):
    s1 = sistema.sessoes.obter("5511900000001", None, sistema.relogio())
    s2 = sistema.sessoes.obter("5511900000002", None, sistema.relogio())
    saida, erro = sistema.ferr.executar(
        "criar_reserva",
        {"procedimento_id": "consulta_avaliacao", "profissional_id": "dra_ana", "inicio": "2026-11-12T10:00", "nome_paciente": "A"},
        s1,
    )
    assert not erro
    dados = json.loads(saida)
    assert dados["valor_reserva_30pct"] == "R$ 45,00" and dados["status"] == "pendente_pagamento"
    _, erro = sistema.ferr.executar("verificar_pagamento", {"reserva_id": dados["reserva_id"]}, s2)
    assert erro


def test_nao_existe_ferramenta_para_confirmar_pagamento(sistema):
    nomes = {d["name"] for d in sistema.ferr.definicoes()}
    assert not any("confirmar" in n for n in nomes)
    _, erro = sistema.ferr.executar("confirmar_pagamento", {"reserva_id": "X"}, sistema.sessoes.obter("1", None, sistema.relogio()))
    assert erro


def test_erros_de_entrada_viram_tool_result_de_erro(sistema):
    s = sistema.sessoes.obter("5511900000001", None, sistema.relogio())
    _, erro = sistema.ferr.executar("consultar_horarios", {"procedimento_id": "inexistente", "data_inicial": "2026-11-12"}, s)
    assert erro
    _, erro = sistema.ferr.executar("consultar_horarios", {"procedimento_id": "limpeza", "data_inicial": "12/11"}, s)
    assert erro
