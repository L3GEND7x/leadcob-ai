# Asaas — primeira etapa de integração

Provedor escolhido provisoriamente para o mercado brasileiro, sujeito à aprovação comercial do proprietário. A integração atual **somente consulta** cobranças no sandbox. Não cria cobranças, não captura cartão, não altera assinaturas e não confirma pagamentos reais.

Configuração: variável secreta `ASAAS_SANDBOX_API_KEY`. Não inserir a chave no código, documentação ou chat. Sem chave a consulta falha de modo seguro. O host é fixo no sandbox, sem redirecionamentos. Nenhum dado de cartão é necessário.

Referência oficial: https://docs.asaas.com/reference/recuperar-uma-unica-cobranca e https://docs.asaas.com/reference/criar-nova-cobranca

A função de validação exige ID da cobrança, referência externa e cliente previamente vinculados, valor bruto em centavos exatamente igual, status RECEIVED, data válida não futura, cobrança não removida e sem informação de estorno. Recebimento confirmado não equivale à conciliação de saldo líquido após taxas.

Próxima etapa, depois de mesclar #117: persistir o vínculo único de cliente e cobrança externos com o recebível local, por ambiente; emitir cobrança apenas mediante ação humana e conferir duplicidade/resultado incerto antes de qualquer nova tentativa. Implementar webhook autenticado, reconsulta independente, processamento idempotente, tratamento de estornos, chargebacks e taxas. Testar com conta sandbox real antes de habilitar produção. Nunca usar pagamentos sandbox para liberar acesso real.

Os testes desta etapa usam MockTransport, não uma conta Asaas real. Nenhum endpoint público, job, baixa ou renovação automática é ativado.
