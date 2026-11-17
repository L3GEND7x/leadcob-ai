# Limites comerciais

A configuração `COMMERCIAL_ENTITLEMENTS_ENABLED=false` é o padrão. Ativar apenas após homologação, atribuição de assinaturas válidas e configuração de autenticação comercial. Com a flag ativada:

- Gravações no workspace exigem assinatura ativa (HTTP 402 quando ausente, futura, vencida ou cancelada).
- Consulta, logout e supressão de contatos continuam permitidos a usuário autenticado e autorizado. Não há exclusão automática nem bloqueio de acesso aos próprios dados.
- Criações de leads, tarefas, carteiras, títulos, contatos e membros têm cotas de registros armazenados, não franquias mensais de pesquisas ou IA. Contatos suprimidos e tarefas concluídas continuam ocupando armazenamento.
- A organização é bloqueada transacionalmente durante a verificação e gravação. Todas as rotas comerciais novas que criem registros precisam respeitar esta mesma regra. Teste concorrente PostgreSQL ainda é necessário.
- Redução de plano abaixo do consumo não apaga dados; novas criações da categoria ficam impedidas. Um plano desativado não invalida assinaturas existentes. Cadastro inicial do administrador é parte do provisionamento; cotas de membros adicionais são verificadas.
- Não há confirmação de pagamento, gateway, cobrança automática ou ativação de produção nesta entrega.
