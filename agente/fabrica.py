"""Monta o agente com todas as dependências."""
import anthropic

from . import config
from .agenda import Agenda
from .agente import Agente
from .conhecimento import Conhecimento
from .encaminhamento import Encaminhamentos
from .ferramentas import Ferramentas
from .pagamentos import GatewayFake
from .sessoes import RepositorioSessoes


def criar_sistema(demo: bool = False, cliente=None):
    kb = Conhecimento.carregar(config.ARQUIVO_CLINICA)
    agenda = Agenda(kb, GatewayFake(), config.agora)
    if demo:
        agenda.semear_demo()
    encaminhamentos = Encaminhamentos(config.ARQUIVO_ENCAMINHAMENTOS, config.agora)
    ferramentas = Ferramentas(kb, agenda, encaminhamentos, config.agora)
    agente = Agente(cliente or anthropic.Anthropic(), ferramentas, encaminhamentos)
    sessoes = RepositorioSessoes(config.INATIVIDADE_NOVA_CONVERSA_MIN)
    return agente, sessoes, agenda
