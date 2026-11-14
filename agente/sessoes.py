"""Sessões de conversa (uma por telefone), mantidas em memória."""
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .agenda import normalizar_telefone


@dataclass
class Sessao:
    telefone: str
    nome_perfil: str | None
    iniciada_em: datetime
    ultima_atividade: datetime
    mensagens: list = field(default_factory=list)  # histórico enviado ao modelo
    registro: list[str] = field(default_factory=list)  # fatos registrados (resumo p/ humano)
    encaminhado: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)


class RepositorioSessoes:
    """Em produção, troque por Redis/banco para sobreviver a reinícios."""

    def __init__(self, inatividade_min: int):
        self._inatividade = timedelta(minutes=inatividade_min)
        self._sessoes: dict[str, Sessao] = {}
        self._lock = threading.Lock()

    def obter(self, telefone: str, nome_perfil: str | None, agora: datetime) -> Sessao:
        tel = normalizar_telefone(telefone)
        with self._lock:
            sessao = self._sessoes.get(tel)
            if sessao is None or agora - sessao.ultima_atividade > self._inatividade:
                sessao = Sessao(tel, nome_perfil, agora, agora)
                self._sessoes[tel] = sessao
            elif nome_perfil and not sessao.nome_perfil:
                sessao.nome_perfil = nome_perfil
            return sessao
