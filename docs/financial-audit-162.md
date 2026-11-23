# PR #162 — auditoria financeira interna, apenas leitura

## Confirmação antes do desenvolvimento
#161 mesclado e três workflows aprovados. Railway web ainda no commit 75b0dda (PR #152), não sincronizado com os PRs posteriores.

## Problema observado
O produto já possui recebíveis internos, baixas manuais, vínculo Asaas sandbox, caixa de eventos, observações e renovações. Faltava um relatório único, por organização, para conciliar esses registros, identificar pendências e distinguir dinheiro real de simulações do sandbox.

## Implementação
Rota exclusiva de proprietário: GET /api/owner/commercial/organizations/{organization_id}/financial-audit. Reutiliza autenticação do proprietário, consulta até 5.000 recebíveis e não faz chamada ao Asaas nem qualquer escrita no banco. Consolida valores em centavos de recebíveis abertos, vencidos, pagos manualmente com metadados mínimos, anulados e abertos associados ao sandbox. Separa alertas por recebível: reserva sandbox sem vínculo confirmado, lançamento sandbox marcado como pago, baixa incompleta, conflitos de valores de reserva, divergência de referência, renovação irregular e preço do plano atual divergente do preço histórico (este último só para revisão). Inclui campos provider_verified=false e bank_reconciled=false sem exceções.

Testes HTTP adicionados ao cenário financeiro isolado: consulta por organização, não alteração de recebíveis, reserva incerta não convertida em receita e baixa manual sem comprovação bancária. Testes não confirmam banco externo nem pagamento real.

## Implicações
- Não é conciliação bancária. Baixa manual indica somente registro no livro interno.
- Eventos do sandbox não habilitam receita real nem acesso comercial.
- Incompatibilidade com preço atual do plano não é necessariamente erro histórico.
- Não marca faturas pagas, não renova planos, não cancela cobranças nem repete emissão.
- Não atesta conformidade fiscal, emissão de NFS-e, LGPD ou antifraude.
- Relatório em memória é limitado a 5.000 recebíveis/organização; volumetria maior exige exportação paginada e aprovação de escopo.
- Para lançar assinaturas reais, ainda é necessário provedor de produção, verificação da cobrança e liquidação, reconciliação com extrato bancário, trilha de estorno, termos comerciais e verificação tributária.

## Critérios de aceite
CI e testes financeiros PostgreSQL aprovados; revisão de isolamento/autorização, valores exatos em centavos e conflito de vinculações; homologação com dados sintéticos e evidência de que nenhuma rota provoca baixas. Reimplantar main na Railway somente após backup, migrações revistas e janela planejada. Nenhuma implantação nem recebimento real foi realizado.
