"""Núcleo do agente: monta o contexto, conduz o loop de ferramentas e aplica as regras de forma determinística."""
import logging
from datetime import timedelta

import anthropic

from . import agenda as ag
from . import config
from .encaminhamento import Encaminhamentos
from .ferramentas import Ferramentas
from .sessoes import Sessao

log = logging.getLogger(__name__)

MSG_INSTABILIDADE = "Peço desculpas, tive uma instabilidade momentânea. Poderia enviar sua mensagem novamente?"
MSG_RECUSA = (
    "Para que você seja atendido corretamente, estou encaminhando esta conversa a um de nossos atendentes.\n"
    "Eles darão continuidade por aqui em breve."
)
INSTRUCAO_REESCRITA = (
    "Instrução interna do sistema: sua última resposta tem mais de {n} linhas. Reescreva-a em no máximo "
    "{n} linhas, mantendo as informações essenciais (valores, condições de reserva, próximos passos). "
    "Não chame ferramentas."
)


def contar_linhas(texto: str) -> int:
    return len([linha for linha in texto.splitlines() if linha.strip()])


def _tipo(bloco) -> str:
    return getattr(bloco, "type", "")


def conteudo_para_historico(conteudo: list) -> list:
    """Prepara o conteúdo da resposta para voltar ao histórico.

    Se houve fallback no meio da resposta, remove thinking/tool_use anteriores ao último
    bloco `fallback` (que permanece no lugar), conforme a regra de eco da API.
    """
    ultimo = max((i for i, b in enumerate(conteudo) if _tipo(b) == "fallback"), default=-1)
    if ultimo < 0:
        return list(conteudo)
    return [
        b for i, b in enumerate(conteudo)
        if i >= ultimo or _tipo(b) not in ("thinking", "redacted_thinking", "tool_use")
    ]


def extrair_texto(conteudo: list) -> str:
    return "\n".join(b.text for b in conteudo if _tipo(b) == "text").strip()


class RespostaInvalida(Exception):
    pass


class Agente:
    def __init__(self, cliente: anthropic.Anthropic, ferramentas: Ferramentas, encaminhamentos: Encaminhamentos, agora=config.agora, modelo: str = config.MODELO):
        self.cliente = cliente
        self.ferramentas = ferramentas
        self.encaminhamentos = encaminhamentos
        self._agora = agora
        self.modelo = modelo
        self.prompt = config.ARQUIVO_PROMPT.read_text(encoding="utf-8")

    # ---------- API pública ----------
    def responder(self, sessao: Sessao, texto: str) -> str | None:
        """Devolve a resposta ao paciente, ou None se a conversa já está com um humano."""
        with sessao.lock:
            if sessao.encaminhado:
                return None
            agora = self._agora()
            if agora - sessao.iniciada_em > timedelta(minutes=config.LIMITE_CONVERSA_MIN):
                return self._encaminhar_por_tempo(sessao)
            marca = len(sessao.mensagens)
            sessao.mensagens.append({"role": "user", "content": texto})
            try:
                resposta = self._turno(sessao)
            except (anthropic.APIError, RespostaInvalida):
                log.exception("Falha ao gerar resposta para %s", sessao.telefone)
                if len(sessao.mensagens) == marca + 1:  # nada aconteceu além da mensagem do paciente
                    sessao.mensagens.pop()
                return MSG_INSTABILIDADE
            sessao.ultima_atividade = self._agora()
            return resposta

    # ---------- internos ----------
    def _contexto(self, sessao: Sessao) -> str:
        agora = self._agora()
        minutos = int((agora - sessao.iniciada_em).total_seconds() // 60)
        return (
            "## Contexto desta conversa (informado pelo sistema, não pelo paciente)\n"
            f"- Data e hora atuais: {ag.DIAS[agora.weekday()]}, {agora:%d/%m/%Y}, {agora:%H:%M} (horário de Brasília).\n"
            f"- Paciente identificado pelo WhatsApp (final {sessao.telefone[-4:]}); nome no perfil: {sessao.nome_perfil or 'não informado'}.\n"
            f"- A conversa começou há {minutos} minuto(s).\n\n"
            "## Uso das ferramentas\n"
            "- Valores, procedimentos, profissionais, horários e dados da clínica só existem nas ferramentas; nunca use outra fonte.\n"
            "- Só diga que um agendamento está confirmado se verificar_pagamento retornar status 'confirmada'.\n"
            "- Cancelar ou remarcar consultas está fora do seu escopo: use encaminhar_para_humano.\n"
            "- Se uma ferramenta devolver informação null ou indisponível, diga que não tem essa informação e encaminhe."
        )

    def _chamar(self, sessao: Sessao, mensagens: list, **extra):
        params = dict(
            model=self.modelo,
            max_tokens=config.MAX_TOKENS,
            system=[
                {"type": "text", "text": self.prompt},
                {"type": "text", "text": self._contexto(sessao)},
            ],
            tools=self.ferramentas.definicoes(),
            messages=mensagens,
            output_config={"effort": config.ESFORCO},
            **extra,
        )
        if config.USAR_FALLBACK_RECUSA:
            return self.cliente.beta.messages.create(betas=[config.BETA_FALLBACK], fallbacks="default", **params)
        return self.cliente.messages.create(**params)

    def _turno(self, sessao: Sessao) -> str:
        for _ in range(config.MAX_ITERACOES_FERRAMENTAS):
            resp = self._chamar(sessao, sessao.mensagens)
            if resp.stop_reason == "refusal":
                return self._encaminhar(sessao, "Solicitação recusada pelos filtros de segurança do modelo", MSG_RECUSA)
            if resp.stop_reason not in ("end_turn", "tool_use"):
                raise RespostaInvalida(f"stop_reason inesperado: {resp.stop_reason}")
            conteudo = conteudo_para_historico(resp.content)
            sessao.mensagens.append({"role": "assistant", "content": conteudo})
            if resp.stop_reason == "tool_use":
                resultados = []
                for bloco in conteudo:
                    if _tipo(bloco) == "tool_use":
                        saida, erro = self.ferramentas.executar(bloco.name, bloco.input, sessao)
                        resultados.append({"type": "tool_result", "tool_use_id": bloco.id, "content": saida, "is_error": erro})
                if not resultados:
                    raise RespostaInvalida("tool_use sem blocos de ferramenta")
                sessao.mensagens.append({"role": "user", "content": resultados})  # todos os resultados numa só mensagem
                continue
            texto = extrair_texto(conteudo)
            if not texto:
                raise RespostaInvalida("resposta sem texto")
            return self._respeitar_limite_de_linhas(sessao, texto)
        raise RespostaInvalida("limite de iterações de ferramentas atingido")

    def _respeitar_limite_de_linhas(self, sessao: Sessao, texto: str) -> str:
        limite = config.MAX_LINHAS_RESPOSTA
        if contar_linhas(texto) <= limite:
            return texto
        log.warning("Resposta com %d linhas; pedindo reescrita.", contar_linhas(texto))
        instrucao = {"role": "user", "content": INSTRUCAO_REESCRITA.format(n=limite)}
        resp = self._chamar(sessao, sessao.mensagens + [instrucao], tool_choice={"type": "none"})
        if resp.stop_reason != "end_turn":
            raise RespostaInvalida("reescrita falhou")
        conteudo = conteudo_para_historico(resp.content)
        novo = extrair_texto(conteudo)
        if not novo:
            raise RespostaInvalida("reescrita sem texto")
        # Só acrescenta ao histórico (nunca edita o que já foi enviado ao modelo).
        sessao.mensagens.extend([instrucao, {"role": "assistant", "content": conteudo}])
        if contar_linhas(novo) > limite:
            log.warning("Reescrita ainda tem %d linhas.", contar_linhas(novo))
        return novo

    def _encaminhar(self, sessao: Sessao, motivo: str, mensagem: str) -> str:
        resumo = "; ".join(sessao.registro[-5:]) or "nenhum dado adicional além do histórico da conversa"
        self.encaminhamentos.registrar(sessao, motivo, resumo)
        return mensagem

    def _encaminhar_por_tempo(self, sessao: Sessao) -> str:
        resumo = "; ".join(sessao.registro[-5:]) or "seus dados de contato e o histórico da conversa"
        resumo = resumo[:200]
        mensagem = (
            "Para dar continuidade ao seu atendimento, estou encaminhando a conversa a um de nossos atendentes, "
            "pois ela ultrapassou o tempo previsto para o atendimento automático.\n"
            f"Já registrei: {resumo}.\n"
            "Em breve, um atendente dará continuidade por aqui."
        )
        return self._encaminhar(sessao, f"Conversa acima de {config.LIMITE_CONVERSA_MIN} minutos", mensagem)
