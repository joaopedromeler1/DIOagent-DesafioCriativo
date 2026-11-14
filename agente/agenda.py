"""Agenda e reservas.

Regras do prompt garantidas aqui, em código (e não só pelo modelo):
- um horário só fica ocupado quando a reserva é CONFIRMADA, e isso só acontece
  por `confirmar_pagamento`, chamado pelo sistema de pagamento, nunca pelo modelo;
- a disponibilidade é sempre recalculada na hora (nada de horário inventado);
- cada paciente só enxerga as próprias reservas.
"""
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from .conhecimento import Conhecimento

PASSO_MIN = 30
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

PENDENTE = "pendente_pagamento"
CONFIRMADA = "confirmada"
CONFLITO = "conflito_horario"  # pagou, mas o horário foi ocupado antes: atendimento humano


def normalizar_telefone(telefone: str) -> str:
    return re.sub(r"\D", "", telefone or "")


def legivel(inicio: datetime) -> str:
    return f"{DIAS[inicio.weekday()]}, {inicio:%d/%m/%Y} às {inicio:%H:%M}"


@dataclass
class Reserva:
    id: str
    telefone: str
    nome: str
    procedimento_id: str
    profissional_id: str
    inicio: datetime
    fim: datetime
    valor_total: Decimal
    valor_reserva: Decimal
    link_pagamento: str
    status: str = PENDENTE
    criada_em: datetime = field(default_factory=datetime.now)


class Agenda:
    def __init__(self, conhecimento: Conhecimento, gateway, agora: Callable[[], datetime]):
        self.kb = conhecimento
        self.gateway = gateway
        self._agora = agora
        self._reservas: dict[str, Reserva] = {}
        self._lock = threading.RLock()

    # ---------- disponibilidade ----------
    def _inicios_do_dia(self, dia: date, prof: dict, duracao: timedelta):
        ag = prof["agenda"]
        if dia.weekday() not in ag["dias_semana"]:
            return
        for ini_txt, fim_txt in ag["periodos"]:
            h, m = map(int, ini_txt.split(":"))
            ini = datetime(dia.year, dia.month, dia.day, h, m)
            h, m = map(int, fim_txt.split(":"))
            fim = datetime(dia.year, dia.month, dia.day, h, m)
            atual = ini
            while atual + duracao <= fim:
                yield atual
                atual += timedelta(minutes=PASSO_MIN)

    def _ocupado(self, profissional_id: str, inicio: datetime, fim: datetime) -> bool:
        return any(
            r.status == CONFIRMADA
            and r.profissional_id == profissional_id
            and r.inicio < fim
            and inicio < r.fim
            for r in self._reservas.values()
        )

    def _livre(self, prof: dict, inicio: datetime, duracao: timedelta) -> bool:
        if inicio <= self._agora():
            return False
        if inicio not in set(self._inicios_do_dia(inicio.date(), prof, duracao)):
            return False
        return not self._ocupado(prof["id"], inicio, inicio + duracao)

    def horarios_livres(
        self,
        procedimento_id: str,
        de: date,
        ate: date,
        profissional_id: str | None = None,
        limite: int = 8,
    ) -> list[dict]:
        proc = self.kb.procedimento(procedimento_id)
        duracao = timedelta(minutes=proc["duracao_min"])
        ids = [profissional_id] if profissional_id else proc["profissionais"]
        for pid in ids:
            if pid not in proc["profissionais"]:
                raise ValueError(f"O profissional '{pid}' não realiza este procedimento.")
        achados = []
        with self._lock:
            dia = de
            while dia <= ate:
                for pid in ids:
                    prof = self.kb.profissional(pid)
                    for inicio in self._inicios_do_dia(dia, prof, duracao):
                        if self._livre(prof, inicio, duracao):
                            achados.append(
                                {
                                    "profissional_id": pid,
                                    "profissional": prof["nome"],
                                    "inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
                                    "legivel": legivel(inicio),
                                }
                            )
                dia += timedelta(days=1)
        achados.sort(key=lambda h: (h["inicio"], h["profissional_id"]))
        return achados[:limite]

    # ---------- reservas ----------
    def criar_reserva_pendente(
        self,
        telefone: str,
        nome: str,
        procedimento_id: str,
        profissional_id: str,
        inicio: datetime,
    ) -> Reserva:
        proc = self.kb.procedimento(procedimento_id)
        if profissional_id not in proc["profissionais"]:
            raise ValueError("Este profissional não realiza o procedimento escolhido.")
        prof = self.kb.profissional(profissional_id)
        duracao = timedelta(minutes=proc["duracao_min"])
        total, reserva_valor = self.kb.valores(procedimento_id)
        with self._lock:
            if not self._livre(prof, inicio, duracao):
                raise ValueError("Horário indisponível. Consulte os horários novamente.")
            reserva_id = "R" + secrets.token_hex(3).upper()
            link = self.gateway.criar_cobranca(reserva_id, int(reserva_valor * 100))
            reserva = Reserva(
                id=reserva_id,
                telefone=normalizar_telefone(telefone),
                nome=nome.strip(),
                procedimento_id=procedimento_id,
                profissional_id=profissional_id,
                inicio=inicio,
                fim=inicio + duracao,
                valor_total=total,
                valor_reserva=reserva_valor,
                link_pagamento=link,
                criada_em=self._agora(),
            )
            self._reservas[reserva_id] = reserva
            return reserva

    def confirmar_pagamento(self, reserva_id: str) -> Reserva:
        """Chamado SOMENTE pelo webhook do gateway de pagamento (ou pela simulação do CLI)."""
        with self._lock:
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise KeyError(reserva_id)
            if reserva.status != PENDENTE:
                return reserva  # idempotente
            prof = self.kb.profissional(reserva.profissional_id)
            if self._ocupado(prof["id"], reserva.inicio, reserva.fim) or reserva.inicio <= self._agora():
                reserva.status = CONFLITO
            else:
                reserva.status = CONFIRMADA
            return reserva

    def obter(self, reserva_id: str, telefone: str) -> Reserva | None:
        """Devolve a reserva só se pertencer ao telefone informado."""
        with self._lock:
            reserva = self._reservas.get(reserva_id)
        if reserva and reserva.telefone == normalizar_telefone(telefone):
            return reserva
        return None

    def reservas_do_paciente(self, telefone: str) -> list[Reserva]:
        tel = normalizar_telefone(telefone)
        with self._lock:
            return sorted(
                (r for r in self._reservas.values() if r.telefone == tel),
                key=lambda r: r.inicio,
            )

    def ultima_pendente(self, telefone: str) -> Reserva | None:
        pendentes = [r for r in self.reservas_do_paciente(telefone) if r.status == PENDENTE]
        return max(pendentes, key=lambda r: r.criada_em) if pendentes else None

    def semear_demo(self, telefone_demo: str = "5511999990000") -> None:
        """Cria um paciente já agendado e alguns horários ocupados, para demonstração."""
        dia = self._agora().date() + timedelta(days=1)
        while dia.weekday() > 4:
            dia += timedelta(days=1)
        for pid, hora, tel, nome in [
            ("dra_ana", 10, telefone_demo, "Paciente Demo"),
            ("dra_ana", 9, "5511988880000", "Outro Paciente"),
        ]:
            inicio = datetime(dia.year, dia.month, dia.day, hora, 0)
            r = self.criar_reserva_pendente(tel, nome, "consulta_avaliacao", pid, inicio)
            self.confirmar_pagamento(r.id)
