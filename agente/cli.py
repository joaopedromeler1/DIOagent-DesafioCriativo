"""Chat de terminal para testar o agente sem WhatsApp.

    python -m agente.cli --demo

Comandos: /pagar simula o aviso do gateway de que a reserva pendente foi paga; /sair encerra.
"""
import argparse
import logging

from . import config
from .agenda import CONFIRMADA, legivel
from .fabrica import criar_sistema


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--telefone", default="5511999990001")
    ap.add_argument("--nome", default=None)
    ap.add_argument("--demo", action="store_true", help="carrega paciente agendado (telefone 5511999990000) e horários ocupados")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    agente, sessoes, agenda = criar_sistema(demo=args.demo)
    print(f"Chat de teste (modelo {config.MODELO}). Telefone: {args.telefone}. Digite /pagar para simular o pagamento, /sair para encerrar.\n")
    while True:
        try:
            texto = input("Paciente> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto == "/sair":
            break
        if texto == "/pagar":
            reserva = agenda.ultima_pendente(args.telefone)
            if reserva is None:
                print("[simulação] não há reserva pendente.\n")
                continue
            reserva = agenda.confirmar_pagamento(reserva.id)
            print(f"[simulação] gateway confirmou o pagamento de {reserva.id}: status {reserva.status} ({legivel(reserva.inicio)})\n")
            continue
        sessao = sessoes.obter(args.telefone, args.nome, config.agora())
        resposta = agente.responder(sessao, texto)
        print(f"\nClínica> {resposta}\n" if resposta else "\n[conversa com atendente humano: o agente não responde mais]\n")


if __name__ == "__main__":
    main()
