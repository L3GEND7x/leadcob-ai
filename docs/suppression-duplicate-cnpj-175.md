# PR #175 — supressão por CNPJ compartilhada entre registros duplicados

## Falha observada antes da correção
Em `routes_contacts.py`, `is_blocked` verificava apenas `Suppression.company_id == company.id` ou `Suppression.cnpj == company.cnpj` literalmente. Se um CNPJ aparecesse em dois registros `Company` e o proprietário suprimisse somente o ID da matriz, a filial duplicada continuava disponível para operações diretas, pesquisa de site, cadastro de contatos e visualização. A lista `GET /api/contacts` excluía apenas o ID marcado, não os registros irmãos do mesmo CNPJ. CNPJs alfanuméricos divergentes por caixa também podiam escapar da comparação literal.

## Correção
- `contact_suppression.is_suppressed` examina opt-out por ID, CNPJ explícito normalizado e CNPJ do registro `Company` associado à supressão. A comparação normaliza pontuação usual e caixa de CNPJ alfanumérico.
- `suppression_keys` padroniza chaves para consultas em lote. A lista de contatos restringe toda a família do CNPJ antes de calcular totais, cobertura ou entregar itens.
- Todas as rotas que já chamavam `is_blocked` — cadastro, revisão, descoberta manual, mapa, pesquisa de domínio e confirmação — passam a respeitar o mesmo opt-out. Sincronização também reutiliza o bloqueio existente.
- Teste HTTP sintético exercita matriz e filial com CNPJ igual, supressão por ID e por CNPJ com caixa diferente, bloqueio da descoberta sem chamar o site, e integridade da empresa independente.

## Limites
A supressão é global dentro deste ambiente do proprietário. Isso **não substitui** o opt-out e as permissões por assinante do workspace comercial. Dados legados fora dos formatos usuais de CNPJ precisam ser saneados; campos `cnpj` do modelo têm comprimento máximo 14. Nenhuma coleta externa, alteração de banco ou revogação real de dados foi executada. Para conformidade LGPD é necessário revisar políticas de exclusão/retenção e outras interfaces que possam expor empresas suprimidas.

## GO/NO-GO
Exigir CI verde, testes em navegador e PostgreSQL. Publicar somente a nova imagem web sem trocar credenciais, flags ou configurações do Postgres. O teste sintético não prova a qualidade dos registros reais de Manaus.
