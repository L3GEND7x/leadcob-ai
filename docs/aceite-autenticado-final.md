# Aceite autenticado final (proprietário)

Com a revisão be5a6b0 implantada, o comando abaixo pode ser executado do
repositório atualizado sem instalar um novo serviço ou compartilhar senha.

```sh
cd backend
python -m app.jobs.final_owner_acceptance --expected-sha be5a6b0d481169f16961a174ea2d3229a0a81c0f
```

Instale requirements.txt antes, se necessário. Acrescente --test-ai somente
para autorizar uma geração de diagnóstico com custo limitado pelo orçamento
existente. A simulação usa R$ 1.000, multa 2%, juros 1% e entrada R$ 130;
espera R$ 1.030 e três parcelas de R$ 300. Não cria título ou movimentação.
O diagnóstico de IA usa a rota já publicada, não envia dados de clientes,
e registra auditoria e consumo. A senha é digitada no terminal, nunca no chat.
O JSON de saída contém somente indicadores, não registros de empresas.

No celular, entre no painel e abra Assistente IA. Use Verificar acesso ao
modelo e Testar resposta real da IA (pode consumir orçamento). Depois teste
uma pergunta de resumo do painel, sem enviar dados de terceiros. A geração
sintética não comprova chamada de ferramentas em uma conversa normal.

A comprovação de inventário e contactos exige os resultados autenticados.
Não usar como contagem oficial nacional. A validação financeira sintética
não comprova pagamentos reais, carteiras de clientes ou isolamento multiempresa.
