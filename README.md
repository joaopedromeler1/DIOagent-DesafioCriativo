# DIOagent-DesafioCriativo

Agente de atendimento para clínicas odontológicas via WhatsApp, construído com a API da Claude (Python).
O texto do agente está em [`prompts/system-prompt.md`](prompts/system-prompt.md) e é carregado como instrução de sistema.

## Como as regras do prompt são garantidas

O prompt orienta o modelo, mas as regras críticas também são aplicadas em código:

| Regra | Onde é garantida |
|---|---|
| Só confirmar agendamento após pagar 30% | `Agenda`: a reserva nasce *pendente* e só vira *confirmada* via `confirmar_pagamento`, chamado pelo gateway. Não existe ferramenta para o modelo confirmar. |
| Nunca inventar horários | `consultar_horarios` calcula a disponibilidade real; `criar_reserva` revalida o horário. |
| Horário só ocupado após condições cumpridas | Reservas pendentes não bloqueiam a agenda. |
| Valores e informações oficiais | Só saem das ferramentas, a partir de `data/clinica.json`. Campos `null` = indisponível, e o agente encaminha. |
| Privacidade entre pacientes | O telefone vem da sessão do WhatsApp, nunca de parâmetro do modelo. |
| Máximo de 4 linhas | `Agente` conta as linhas e pede uma reescrita se passar. |
| Encaminhar após 30 minutos | `Agente` verifica o tempo antes de cada turno e transfere sem chamar o modelo. |
| Encaminhamento para humano | `encaminhar_para_humano` grava em `data/encaminhamentos.jsonl` e o agente deixa de responder nessa conversa. |

## Estrutura

```
prompts/system-prompt.md   prompt do agente (texto original)
data/clinica.json          base oficial da clínica (DADOS FICTÍCIOS: substitua)
agente/
  config.py                modelo, limites, arquivos
  conhecimento.py          procedimentos, valores, cálculo dos 30%
  agenda.py                disponibilidade e reservas (pendente -> confirmada)
  pagamentos.py            gateway de pagamento (fake; troque pelo real)
  ferramentas.py           ferramentas expostas ao modelo
  agente.py                loop do modelo + regras determinísticas
  sessoes.py               sessões por telefone
  encaminhamento.py        registro de transferências para humano
  cli.py                   chat de terminal para testes
  whatsapp.py              webhooks da WhatsApp Cloud API e do pagamento
tests/                     27 testes (sem chamar a API)
docs/                      modelo da base de conhecimento e cenários de teste
```

## Como rodar

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # chave da API
python -m agente.cli --demo         # chat no terminal; /pagar simula o pagamento
python -m pytest                    # testes
```

O modelo padrão é `claude-opus-5-5` (troque com `AGENTE_MODELO`). Se um filtro de segurança recusar a requisição, o
fallback server-side da API tenta de novo em outro modelo; desligue com `AGENTE_FALLBACK_RECUSA=0`.

### WhatsApp

```bash
cp .env.example .env   # preencha e exporte as variáveis
uvicorn agente.whatsapp:app --port 8000
```

1. Na Meta for Developers, aponte o webhook para `https://SEU-DOMINIO/webhook` com o mesmo `WHATSAPP_VERIFY_TOKEN`.
2. Faça o gateway de pagamento chamar `POST /pagamentos/webhook` com `{"reserva_id": "..."}` e o header `X-Webhook-Secret`.

## O que falta para produção

- **Dados reais** em `data/clinica.json` (valores, profissionais, orientações, política de cancelamento).
- **Agenda e sessões persistentes**: hoje ficam em memória e somem ao reiniciar. Troque `Agenda` e `RepositorioSessoes` por banco/Redis, ou integre com o sistema da clínica.
- **Gateway de pagamento real** no lugar do `GatewayFake`.
- **Aviso em tempo real à equipe** quando houver encaminhamento (hoje só grava o arquivo).
- Cancelamento e remarcação ainda vão para atendimento humano.
- O fluxo com a API da Claude e com a Meta ainda não foi testado de ponta a ponta; os testes usam um cliente simulado.
