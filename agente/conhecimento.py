"""Base de conhecimento oficial da clínica (carregada de um JSON)."""
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PERCENTUAL_RESERVA = Decimal("0.30")


def calcular_reserva(valor_total: Decimal) -> Decimal:
    """Reserva de 30% do valor do serviço, arredondada para centavos."""
    return (Decimal(valor_total) * PERCENTUAL_RESERVA).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def brl(valor: Decimal) -> str:
    """Formata em reais: 1234.5 -> 'R$ 1.234,50'."""
    texto = f"{Decimal(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


class Conhecimento:
    def __init__(self, dados: dict):
        self.clinica = dados["clinica"]
        self._profissionais = {p["id"]: p for p in dados["profissionais"]}
        self._procedimentos = {p["id"]: p for p in dados["procedimentos"]}

    @classmethod
    def carregar(cls, caminho: Path) -> "Conhecimento":
        return cls(json.loads(Path(caminho).read_text(encoding="utf-8")))

    def procedimento(self, procedimento_id: str) -> dict:
        try:
            return self._procedimentos[procedimento_id]
        except KeyError:
            ids = ", ".join(self._procedimentos)
            raise ValueError(f"Procedimento '{procedimento_id}' não existe. Opções: {ids}.")

    def profissional(self, profissional_id: str) -> dict:
        try:
            return self._profissionais[profissional_id]
        except KeyError:
            raise ValueError(f"Profissional '{profissional_id}' não existe.")

    def valores(self, procedimento_id: str) -> tuple[Decimal, Decimal]:
        total = Decimal(str(self.procedimento(procedimento_id)["valor_total"]))
        return total, calcular_reserva(total)

    def listar_procedimentos(self) -> list[dict]:
        saida = []
        for proc in self._procedimentos.values():
            total, reserva = self.valores(proc["id"])
            saida.append(
                {
                    "id": proc["id"],
                    "nome": proc["nome"],
                    "duracao_min": proc["duracao_min"],
                    "profissionais": [
                        {"id": pid, "nome": self.profissional(pid)["nome"]}
                        for pid in proc["profissionais"]
                    ],
                    "valor_total": brl(total),
                    "valor_reserva_30pct": brl(reserva),
                    "orientacoes": proc["orientacoes"],  # null = não disponível
                }
            )
        return saida
