"""Configurações do agente, lidas de variáveis de ambiente."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent

# Modelo e parâmetros da chamada à API.
MODELO = os.getenv("AGENTE_MODELO", "claude-opus-5-5")
ESFORCO = os.getenv("AGENTE_ESFORCO", "medium")  # low | medium | high
MAX_TOKENS = int(os.getenv("AGENTE_MAX_TOKENS", "8000"))
MAX_ITERACOES_FERRAMENTAS = 8
# Re-executa a requisição em outro modelo se um classificador de segurança recusar.
USAR_FALLBACK_RECUSA = os.getenv("AGENTE_FALLBACK_RECUSA", "1") == "1"
BETA_FALLBACK = "server-side-fallback-2026-07-01"

# Regras de negócio do prompt.
LIMITE_CONVERSA_MIN = 30  # acima disso, encaminha para humano
INATIVIDADE_NOVA_CONVERSA_MIN = 120  # silêncio acima disso inicia uma nova conversa
MAX_LINHAS_RESPOSTA = 4

# Arquivos.
ARQUIVO_PROMPT = RAIZ / "prompts" / "system-prompt.md"
ARQUIVO_CLINICA = Path(os.getenv("AGENTE_DADOS_CLINICA", RAIZ / "data" / "clinica.json"))
ARQUIVO_ENCAMINHAMENTOS = Path(
    os.getenv("AGENTE_ENCAMINHAMENTOS", RAIZ / "data" / "encaminhamentos.jsonl")
)

FUSO = ZoneInfo(os.getenv("AGENTE_FUSO", "America/Sao_Paulo"))


def agora() -> datetime:
    """Data/hora local da clínica, sem fuso (a agenda trabalha em horário local)."""
    return datetime.now(FUSO).replace(tzinfo=None)
