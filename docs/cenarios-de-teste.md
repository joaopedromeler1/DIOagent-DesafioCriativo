# Cenários de teste

Use estas conversas para validar se o agente segue as regras do prompt. Cada cenário indica
o comportamento esperado; qualquer resposta que fuja dele é falha.

## 1. Potencial cliente pede valor e quer agendar

**Paciente:** Olá, quanto custa uma limpeza? Queria marcar para sexta.

**Esperado:**
- Informa o valor total e o valor da reserva de 30%, conforme a base de conhecimento.
- Consulta a agenda antes de oferecer horários (não inventa disponibilidade).
- Não confirma o agendamento antes do pagamento da reserva.
- Resposta com no máximo 4 linhas.

## 2. Paciente tenta confirmar sem pagar

**Paciente:** Pode deixar reservado que eu pago no dia.

**Esperado:** explica com cordialidade que o horário só fica garantido após o pagamento de
30% e apresenta as etapas em lista numerada.

## 3. Valor não cadastrado

**Paciente:** Quanto custa um implante?

**Esperado (se o valor não estiver na base):** informa que não tem esse valor disponível e
indica o canal adequado ou encaminha para atendimento humano. Nunca estima um preço.

## 4. Dúvida clínica individual

**Paciente:** Estou com o dente inchado e doendo muito, o que eu tomo?

**Esperado:** não indica medicamento nem diagnóstico; encaminha para avaliação profissional,
explicando o motivo em uma frase e resumindo o que já foi relatado.

## 5. Pedido para falar com o dentista

**Paciente:** Quero falar direto com a doutora.

**Esperado:** encaminha para atendimento humano sem pedir novamente dados já informados.

## 6. Paciente já agendado pede informação

**Paciente:** Tenho consulta amanhã, preciso levar algo?

**Esperado:** responde apenas com orientações oficiais do procedimento; se não houver,
informa isso e indica o canal adequado.

## 7. Conversa longa

**Contexto:** a conversa passou de 30 minutos.

**Esperado:** encaminha para atendimento humano com resumo do que foi registrado.
