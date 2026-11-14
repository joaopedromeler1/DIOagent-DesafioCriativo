"""Ferramentas que o modelo pode chamar.

O modelo nunca recebe o telefone como parâmetro: ele vem da sessão (WhatsApp), então um
paciente não consegue consultar dados de outro. Também não existe ferramenta para
confirmar pagamento: quem confirma é o gateway, via `Agenda.confirmar_pagamento`.
"""
import json
import logging
from datetime import datetime, timedelta

from . import agenda as ag
from .conhecimento import Conhecimento, brl
from .encaminhamento import Encaminhamentos
from .sessoes import Sessao

log = logging.getLogger(__name__)

_SEM_PARAMS = {"type": "object", "properties": {}, "additionalProperties": False}

DEFINICOES = [
    {
        "name": "informacoes_clinica",
        "description": "Dados oficiais da clínica: endereço, horário de funcionamento, canal de atendimento humano, formas de pagamento da reserva e política de cancelamento. Valores null significam informação indisponível.",
        "input_schema": _SEM_PARAMS,
    },
    {
        "name": "listar_procedimentos",
        "description": "Lista os procedimentos oficiais com duração, profissionais responsáveis, valor total, valor da reserva (30%) e orientações. Única fonte permitida de valores e dados de procedimentos.",
        "input_schema": _SEM_PARAMS,
    },
    {
        "name": "consultar_horarios",
        "description": "Consulta a disponibilidade REAL da agenda para um procedimento. Devolve até 8 horários livres a partir da data inicial. Sempre use antes de oferecer qualquer horário.",
        "input_schema": {
            "type": "object",
            "properties": {
                "procedimento_id": {"type": "string", "description": "ID retornado por listar_procedimentos."},
                "data_inicial": {"type": "string", "description": "Primeira data da busca, formato AAAA-MM-DD."},
                "dias": {"type": "integer", "description": "Quantos dias à frente buscar (1 a 30). Padrão 7."},
                "profissional_id": {"type": "string", "description": "Opcional: restringe a um profissional."},
            },
            "required": ["procedimento_id", "data_inicial"],
            "additionalProperties": False,
        },
    },
    {
        "name": "criar_reserva",
        "description": "Cria uma reserva PENDENTE de pagamento e devolve o link de pagamento da reserva de 30%. NÃO confirma nem bloqueia o horário: ele só fica garantido depois que o pagamento for confirmado (use verificar_pagamento). Chame apenas depois que o paciente escolher procedimento, profissional, horário e informar o nome completo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "procedimento_id": {"type": "string"},
                "profissional_id": {"type": "string"},
                "inicio": {"type": "string", "description": "Horário exato devolvido por consultar_horarios, formato AAAA-MM-DDTHH:MM."},
                "nome_paciente": {"type": "string", "description": "Nome completo informado pelo paciente."},
            },
            "required": ["procedimento_id", "profissional_id", "inicio", "nome_paciente"],
            "additionalProperties": False,
        },
    },
    {
        "name": "verificar_pagamento",
        "description": "Consulta o status de uma reserva. Só trate o agendamento como confirmado se o status for 'confirmada'.",
        "input_schema": {
            "type": "object",
            "properties": {"reserva_id": {"type": "string"}},
            "required": ["reserva_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consultar_meus_agendamentos",
        "description": "Lista os agendamentos e reservas do paciente desta conversa (identificado pelo telefone do WhatsApp).",
        "input_schema": _SEM_PARAMS,
    },
    {
        "name": "encaminhar_para_humano",
        "description": "Transfere a conversa para um atendente humano. Use quando o paciente pedir o dentista, a solicitação estiver fora do escopo (ex.: cancelar ou remarcar), faltar informação oficial, ou for preciso avaliação clínica individual. Depois de chamar, escreva a mensagem final ao paciente com o motivo em uma frase e o que já foi registrado, sem pedir dados novamente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Motivo do encaminhamento, em uma frase."},
                "resumo": {"type": "string", "description": "Resumo do que já foi informado e registrado na conversa (nome, procedimento, horários, pagamento)."},
            },
            "required": ["motivo", "resumo"],
            "additionalProperties": False,
        },
    },
]


class Ferramentas:
    def __init__(self, conhecimento: Conhecimento, agenda: ag.Agenda, encaminhamentos: Encaminhamentos, agora):
        self.kb = conhecimento
        self.agenda = agenda
        self.encaminhamentos = encaminhamentos
        self._agora = agora

    def definicoes(self) -> list[dict]:
        return DEFINICOES

    def executar(self, nome: str, entrada: dict, sessao: Sessao) -> tuple[str, bool]:
        """Devolve (conteúdo, é_erro). Erros viram tool_result com is_error, nunca exceção."""
        try:
            metodo = getattr(self, f"_{nome}", None)
            if metodo is None or nome not in {d["name"] for d in DEFINICOES}:
                return f"Ferramenta desconhecida: {nome}", True
            resultado = metodo(sessao, **(entrada or {}))
            return json.dumps(resultado, ensure_ascii=False), False
        except (ValueError, TypeError, KeyError) as e:
            return f"Erro: {e}", True
        except Exception:  # noqa: BLE001 - nunca derrubar a conversa por falha de ferramenta
            log.exception("Falha inesperada na ferramenta %s", nome)
            return "Erro interno ao executar a ferramenta. Encaminhe para atendimento humano.", True

    # ---------- implementações ----------
    def _informacoes_clinica(self, sessao: Sessao) -> dict:
        return self.kb.clinica

    def _listar_procedimentos(self, sessao: Sessao) -> list[dict]:
        return self.kb.listar_procedimentos()

    def _consultar_horarios(self, sessao, procedimento_id, data_inicial, dias=7, profissional_id=None) -> dict:
        try:
            de = datetime.strptime(data_inicial, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("data_inicial deve estar no formato AAAA-MM-DD.")
        dias = max(1, min(int(dias), 30))
        horarios = self.agenda.horarios_livres(procedimento_id, de, de + timedelta(days=dias - 1), profissional_id)
        nome = self.kb.procedimento(procedimento_id)["nome"]
        sessao.registro.append(f"Consultou horários de {nome} a partir de {de:%d/%m}")
        if not horarios:
            return {"horarios": [], "observacao": "Nenhum horário livre nesse período. Ofereça outro período ou encaminhe para atendimento humano."}
        return {"horarios": horarios}

    def _criar_reserva(self, sessao, procedimento_id, profissional_id, inicio, nome_paciente) -> dict:
        if not str(nome_paciente).strip():
            raise ValueError("Informe o nome completo do paciente.")
        try:
            inicio_dt = datetime.strptime(inicio, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise ValueError("inicio deve estar no formato AAAA-MM-DDTHH:MM.")
        r = self.agenda.criar_reserva_pendente(sessao.telefone, nome_paciente, procedimento_id, profissional_id, inicio_dt)
        proc = self.kb.procedimento(procedimento_id)
        sessao.registro.append(f"Reserva {r.id} ({proc['nome']}, {ag.legivel(r.inicio)}) aguardando pagamento de {brl(r.valor_reserva)}")
        return {
            "reserva_id": r.id,
            "status": r.status,
            "procedimento": proc["nome"],
            "profissional": self.kb.profissional(r.profissional_id)["nome"],
            "data_hora": ag.legivel(r.inicio),
            "valor_total": brl(r.valor_total),
            "valor_reserva_30pct": brl(r.valor_reserva),
            "link_pagamento": r.link_pagamento,
            "importante": "O horário NÃO está reservado. Ele só será garantido após a confirmação do pagamento da reserva.",
        }

    def _verificar_pagamento(self, sessao, reserva_id) -> dict:
        r = self.agenda.obter(reserva_id, sessao.telefone)
        if r is None:
            raise ValueError("Reserva não encontrada para este paciente.")
        base = {"reserva_id": r.id, "status": r.status, "data_hora": ag.legivel(r.inicio)}
        if r.status == ag.CONFIRMADA:
            sessao.registro.append(f"Reserva {r.id} confirmada")
            base["mensagem"] = "Pagamento confirmado e agendamento garantido."
        elif r.status == ag.PENDENTE:
            base["mensagem"] = "Pagamento ainda não identificado. O horário NÃO está reservado."
            base["link_pagamento"] = r.link_pagamento
        else:
            base["mensagem"] = "O pagamento foi identificado, mas o horário foi ocupado antes. Encaminhe para atendimento humano para tratar do caso."
        return base

    def _consultar_meus_agendamentos(self, sessao: Sessao) -> dict:
        itens = []
        for r in self.agenda.reservas_do_paciente(sessao.telefone):
            itens.append(
                {
                    "reserva_id": r.id,
                    "status": r.status,
                    "procedimento": self.kb.procedimento(r.procedimento_id)["nome"],
                    "profissional": self.kb.profissional(r.profissional_id)["nome"],
                    "data_hora": ag.legivel(r.inicio),
                }
            )
        return {"agendamentos": itens}

    def _encaminhar_para_humano(self, sessao: Sessao, motivo: str, resumo: str) -> dict:
        self.encaminhamentos.registrar(sessao, motivo, resumo)
        return {"encaminhado": True, "instrucao": "Escreva a mensagem final: motivo em uma frase, o que já foi registrado, sem pedir dados novamente."}
