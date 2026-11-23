# PR #163 — Fechamento técnico e aceite de liberação (23/11/2026)

## Evidências obtidas antes da mudança
- PR #161: merged, três workflows verdes.
- PR #162: merged em `5e640a50ec876e0234d25f16463b1d9fb35edb0c`, três workflows verdes. No CI do #162, backend: 271 testes, PostgreSQL financeiro: 7 testes, browser e implantação: sucesso.
- Railway, serviço `leadcob-web`: último deploy bem-sucedido confirmado em `75b0dda48053042a9b03689c54c58e4f5ad3c53a`, correspondente ao #152. O código no ar NÃO corresponde ainda ao código atualizado.
- Serviço de backup Railway: logs em 23/11/2026 registraram dump PostgreSQL (1.581 MiB), snapshot Restic criptografado `6e20e673` às 04:01 UTC, `restic check` de packs, árvores e blobs sem erro, 14 snapshots. Isso NÃO comprova restauração específica do último snapshot.
- Railway tem PostgreSQL e web em estado online e configuração `preDeployCommand=alembic -c /app/alembic.ini upgrade head`, health `/api/health`. Emissão sandbox e banco real são fluxos diferentes; não há comprovação de provedor de pagamento de produção.
- Flags comerciais `COMMERCIAL_AUTH_ENABLED`, `COMMERCIAL_ENTITLEMENTS_ENABLED`, `WORKSPACE_REGISTRY_SEARCH_ENABLED` e `WORKSPACE_ASSISTANT_ENABLED` não constavam entre os nomes de variáveis definidos para o web. Pelos defaults do código, permanecem desativadas.

## O que o #163 adiciona
1. Exposição opcional do commit Railway no JSON de /api/health (`revision` é SHA de 40 caracteres ou `null`, sem segredos), para confrontar com o commit efetivamente implantado.
2. `python -m app.jobs.release_smoke --base-url https://leadcob-web-production.up.railway.app [--expected-sha SHA]`: somente chamadas GET anônimas; verifica banco via health, página inicial, recursos estáticos, indisponibilidade da área comercial quando flag estiver off, endpoints privados bloqueados e sessão anônima não autenticada. Não segue redirecionamentos. Com flag ativada usar `--commercial-enabled`, só após homologação. Retorna código de erro quando falha.
3. Testes sintéticos que rejeitam divulgação não autorizada e versão divergente, impedem URLs perigosas e validam head único das migrações e tabelas críticas.

## Ordem operacional obrigatória
1. CI de #163 deve ficar verde. Mesclar o PR com SHA fixo verificado.
2. Confirmar backup externo recente e testes de restauração em ambiente isolado. Se não for possível restaurar o snapshot mais recente, não afirmar recuperação comprovada.
3. Verificar que migrações Alembic são aditivas e compatíveis com dados existentes; preservar cópia anterior e plano de recuperação.
4. Implantar o commit aprovado; certificar a migração no pre-deploy e o health check. Conferir commit efetivamente implantado e ausência de crashes.
5. Executar smoke HTTP anônimo; verificar controles de acesso manualmente com contas de homologação, autenticação, isolamento de organizações, CRM e banco sem enviar dados reais a terceiros.
6. Só habilitar recursos comerciais, inteligência artificial e worker após aceite explícito de custos, segurança, LGPD, plano de cobrança, banco e cumprimento de políticas externas.

## NO-GO comercial mesmo com CI verde
- A cadeia de backups não foi restaurada a partir do snapshot específico de 23/11 em ambiente separado.
- Provedor de pagamentos de produção, conciliação com extratos reais, estornos e questões fiscais não homologados.
- IA do assinante sem teste real da API e controle de despesas confirmado pelo provedor. Feature flag deve permanecer OFF.
- Pesquisa regional sem comprovação completa de cobertura e procedência dos CNPJs; consulta pelo proprietário não deve vazar CRM para outros assinantes.
- Worker sem serviço produtivo dedicado e teste de filas/leases sob carga.
- Tratamento/retirada LGPD, políticas comerciais, autorização de uso e retenção carecem de revisão final.
- Uma implantação técnica bem-sucedida não é autorização para vender planos ou afirmar ausência de defeitos.

## Rollback
Como a atualização passa por migrações, não basta reinstalar a imagem anterior: código antigo e esquema novo podem ser incompatíveis. Havendo erro, bloquear acesso de escrita/novos pagamentos, preservar evidências, restaurar banco **em ambiente isolado**, comparar migrações e coordenar recuperação transacional; não executar downgrade destrutivo. Não habilitar comerciais por pressão de cronograma.
