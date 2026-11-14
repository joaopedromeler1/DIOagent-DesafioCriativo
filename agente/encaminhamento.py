"""Registro de encaminhamentos para atendimento humano."""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from .sessoes import Sessao

log = logging.getLogger(__name__)


class Encaminhamentos:
    """Grava cada encaminhamento em JSONL e marca a sessão como transferida.

    A partir daí o agente deixa de responder naquela conversa. Para avisar a equipe
    em tempo real (fila do WhatsApp, Slack, e-mail), estenda `registrar`.
    """

    def __init__(self, arquivo: Path, agora):
        self.arquivo = Path(arquivo)
        self._agora = agora
        self._lock = threading.Lock()

    def registrar(self, sessao: Sessao, motivo: str, resumo: str) -> None:
        sessao.encaminhado = True
        evento = {
            "quando": self._agora().isoformat(timespec="seconds"),
            "telefone": sessao.telefone,
            "nome": sessao.nome_perfil,
            "motivo": motivo,
            "resumo": resumo,
            "fatos_registrados": sessao.registro,
        }
        with self._lock:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            with self.arquivo.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        log.info("Conversa %s encaminhada para humano: %s", sessao.telefone, motivo)
