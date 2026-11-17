# Homologação Asaas

O CI geral do #133 falhou na coleta de testes browser por falta do Playwright. O job dedicado de navegador e PostgreSQL passaram; o #134 restringe o job backend à pasta tests e mantém o browser separado.

Para verificar uma cobrança de teste previamente existente, no diretório backend, configure ASAAS_SANDBOX_API_KEY exclusivamente no ambiente local (não no histórico de comandos nem no Git) e execute:

`python -m app.services.asaas_sandbox_probe --payment-id pay_EXEMPLO --customer-id cus_EXEMPLO --reference REFERENCIA --amount-cents 2700`

Substitua os identificadores pelos dados de teste. O utilitário faz apenas GET no host sandbox fixo, sem baixa, renovação ou criação de cobrança. Saída classifica divergência e estado; sucesso não comprova saldo bancário. Não imprima chaves. Teste automatizado usa transporte simulado explicitamente.

Aceite manual ainda necessário: comprovar Pix e boleto no sandbox; autenticação e entrega de webhook, reentrega, valores divergentes, timeout e recuperação por referência externa, estornos e revisão de chargeback. Registrar evidência sem segredos. Não ativar integração de produção. Nenhuma homologação externa executada nesta entrega.
