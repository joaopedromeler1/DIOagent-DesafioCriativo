# DIOagent-DesafioCriativo

Criação de um agente chatbot de atendimento para clínicas odontológicas via WhatsApp.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| [`prompts/system-prompt.md`](prompts/system-prompt.md) | System prompt do agente: identidade, tom de voz, regras de agendamento e encaminhamento. |
| [`docs/base-de-conhecimento.md`](docs/base-de-conhecimento.md) | Modelo com os dados oficiais da clínica (valores, profissionais, políticas) que o agente pode usar. |
| [`docs/cenarios-de-teste.md`](docs/cenarios-de-teste.md) | Conversas de teste para validar o comportamento do agente. |

## Destaques do agente

- **Foco em conversão** sem abrir mão da organização da agenda.
- **Reserva obrigatória de 30%** antes de confirmar qualquer agendamento.
- **Zero invenção:** valores, horários e orientações vêm só da base oficial.
- **Encaminhamento para humano** em casos clínicos, pedidos ao dentista, falta de informação ou conversas acima de 30 minutos.
- **Respostas curtas** (até 4 linhas), formais e acolhedoras.

## Como usar

1. Preencha `docs/base-de-conhecimento.md` com os dados reais da clínica.
2. Configure `prompts/system-prompt.md` como instrução de sistema na plataforma escolhida.
3. Anexe a base de conhecimento ao agente e conecte as integrações de agenda e pagamento.
4. Rode os cenários de `docs/cenarios-de-teste.md` antes de colocar em produção.
