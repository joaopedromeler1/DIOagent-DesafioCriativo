from datetime import datetime
from types import SimpleNamespace

import pytest

from agente import config
from agente.agenda import Agenda
from agente.agente import Agente
from agente.conhecimento import Conhecimento
from agente.encaminhamento import Encaminhamentos
from agente.ferramentas import Ferramentas
from agente.pagamentos import GatewayFake
from agente.sessoes import RepositorioSessoes

# Quarta-feira, 12/11/2026, 09:00
AGORA = datetime(2026, 11, 11, 9, 0)


class Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class ClienteFalso:
    """Cliente roteirizado: cada chamada consome a próxima resposta."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._criar))
        self.messages = SimpleNamespace(create=self._criar)

    def _criar(self, **kw):
        self.chamadas.append(kw)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def texto(t, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=t)])


def usa_ferramenta(nome, entrada, id="tu_1"):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=id, name=nome, input=entrada)],
    )


@pytest.fixture
def relogio():
    return Relogio(AGORA)


@pytest.fixture
def sistema(tmp_path, relogio):
    kb = Conhecimento.carregar(config.ARQUIVO_CLINICA)
    agenda = Agenda(kb, GatewayFake("https://pg.teste/"), relogio)
    enc = Encaminhamentos(tmp_path / "enc.jsonl", relogio)
    ferr = Ferramentas(kb, agenda, enc, relogio)
    sessoes = RepositorioSessoes(120)

    def montar_agente(respostas):
        cliente = ClienteFalso(respostas)
        return Agente(cliente, ferr, enc, agora=relogio), cliente

    return SimpleNamespace(kb=kb, agenda=agenda, enc=enc, ferr=ferr, sessoes=sessoes, agente=montar_agente, relogio=relogio, tmp=tmp_path)
