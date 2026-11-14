# Base de conhecimento da clínica (modelo)

> Na implementação, esses dados vivem em `data/clinica.json` (hoje com valores fictícios). Este documento descreve o que precisa ser preenchido.

O agente só pode responder com informações oficiais. Preencha este modelo com os dados reais
da clínica e envie-o junto com o system prompt (ou carregue-o como base de conhecimento/RAG).
Tudo que estiver entre `[colchetes]` precisa ser substituído; o que ficar vazio o agente deve
tratar como "informação indisponível" e encaminhar para atendimento humano.

## Dados da clínica

- Nome: [nome da clínica]
- Endereço: [endereço completo]
- Horário de funcionamento: [ex.: seg a sex, 8h às 18h; sáb, 8h às 12h]
- Canal de atendimento humano: [telefone, ramal ou fila do WhatsApp]
- Formas de pagamento da reserva (30%): [Pix, cartão, link de pagamento]
- Política de cancelamento e reembolso da reserva: [regra oficial]

## Profissionais

| Profissional | Especialidade | Dias de atendimento |
|---|---|---|
| [Dr(a). Nome] | [especialidade] | [dias] |

## Procedimentos e valores

| Procedimento | Duração | Profissional | Valor total | Reserva (30%) | Orientações pré/pós |
|---|---|---|---|---|---|
| Consulta de avaliação | [min] | [nome] | R$ [valor] | R$ [valor × 0,3] | [orientações] |
| Limpeza (profilaxia) | [min] | [nome] | R$ [valor] | R$ [valor × 0,3] | [orientações] |
| Clareamento | [min] | [nome] | R$ [valor] | R$ [valor × 0,3] | [orientações] |

## Integrações esperadas

O prompt exige "verificar a disponibilidade real" e "confirmar pagamento". Isso só é possível
se o agente tiver ferramentas conectadas, por exemplo:

1. **Consultar agenda** (Google Calendar, sistema da clínica) para listar horários livres.
2. **Gerar cobrança da reserva** e **verificar status do pagamento**.
3. **Encaminhar para humano**, enviando o resumo da conversa.
4. **Registro de horário de início da conversa**, para aplicar a regra dos 30 minutos.

Sem essas ferramentas, o agente deve apenas coletar os dados e encaminhar para um atendente.
