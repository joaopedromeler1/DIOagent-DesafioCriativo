"""Gateway de pagamento da reserva.

`GatewayFake` apenas gera um link de exemplo. Em produção, implemente a mesma
interface (criar_cobranca) com o provedor real (Pix, Mercado Pago, Stripe...) e
chame `Agenda.confirmar_pagamento` quando o webhook do provedor avisar o pagamento.
"""
import os


class GatewayFake:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv(
            "PAGAMENTO_BASE_URL", "https://pagamento.exemplo.invalid/pix/"
        )

    def criar_cobranca(self, reserva_id: str, valor_centavos: int) -> str:
        return f"{self.base_url}{reserva_id}"
