# Continuidade entre IAs — entrega de 27/11/2026

Fotografia verificada em 25/11/2026. Atualizar a partir de GitHub/Railway antes
de qualquer execução. Objetivo imediato: uso interno seguro pelo proprietário;
liberação comercial multiempresa e cobertura nacional integral têm gates próprios.

## Evidências e estado

- Main: 97ec446204c728ce080fa84723e13e4f8e5a4563 (merge #198).
- Railway leadcob-web: mesmo SHA, SUCCESS às 14:08:36 UTC de 25/11.
  URL: https://leadcob-web-production.up.railway.app.
- PR #198: quatro workflows verdes; 329 testes backend aprovados no merge
  sintético do PR. CI específico do commit final de merge não localizado.
- PR #199: aberto no momento desta fotografia; cinco workflows verdes,
  inclusive homologação externa da revisão #198. Verificar estado antes de agir.
- Backup de 25/11: logs do serviço registram dump conferido e restauração
  temporária bem-sucedida; não implica auditoria de todos os dados de negócio.
- Autenticação real, inventário real de Manaus, captação real, contatos,
  geração de IA, CRM completo, simulador em produção e isolamento comercial
  ainda não homologados pelo proprietário.
- Não declarar carga nacional completa. Importadores/manifesto/preflight
  existem, mas carga nacional e staging escalável não comprovados.
- Stack: FastAPI, SQLAlchemy, Alembic, PostgreSQL, frontend JS, Railway.
- Leia COLABORACAO.md e AGENTS.md. Decisão de merge pertence ao proprietário.

## P0 — prompts de execução

### 1. Release e segurança
Confirme main, PRs e CI; integre somente após autorização. Compare SHA de
produção e versão aprovada. Use release_smoke com --expected-sha, HTTPS e
verificação de rotas privadas. Consulte logs e backup; preserve rollback.
Não trocar configuração de serviços nem expor credenciais. Registre evidência
da revisão exata; falha P0/P1 impede aceite.

### 2. Login e módulos autenticados
Execute app.jobs.final_owner_acceptance com SHA efetivamente implantado;
credenciais digitadas pelo proprietário no terminal (nunca chat ou CI).
Confirme login/logout, sessão, CSRF, desktop/mobile e ausência de acesso anônimo.
Execute app.jobs.production_readonly_preflight apenas no ambiente privado
autorizado. Não simule aprovação de produção. Se não houver acesso, entregue
procedimento seguro e declare bloqueio.

### 3. Central de Comando e pesquisa de CNPJs
Audite indicadores e a fonte de cada métrica; diferencie registros, CNPJs
válidos únicos, empresas ativas, prospects e leads qualificados. Valide Manaus
e filtros UF, região, município, CNAE, porte, palavra-chave, paginação,
supressão, duplicatas, CNPJ alfanumérico e exportação. Teste limites de
pontuação/amostra e desempenho; não declare cobertura nacional sem dados.

### 4. Radar e contatos
Audite /api/opportunities, /api/sources e /api/capture/runs. Diferencie
catálogo histórico, captura recente, parcial, falha e nenhum resultado.
Confirme amostra de URLs reais e datas, fontes PNCP e boards configurados.
Não classifique vagas como prova de inadimplência ou terceirização. Em
contatos, valide e-mail funcional, telefone institucional, site e redes
corporativas com origem, data, status e supressão. Não use dados pessoais,
não invente contatos; revisão e teste de entrega são conceitos distintos.

### 5. LeadCoach
Confirme configuração do modelo, limites de orçamento e chave sem revelar
valores. Com autorização de consumo, teste provider-check, generation-check
e conversa normal com ferramentas; valide erros de quota e indisponibilidade,
histórico, permissões e confirmação humana de ações. Não use dados reais de
terceiros no diagnóstico; nunca habilite envio automático.

### 6. CRM, financeiro e comercial
Teste funil, atividades, histórico, follow-up, supressão e exportação com
dados sintéticos em ambiente isolado. Valide simulador sintético em produção:
R$1000, multa 2%, juros 1% por 30 dias, entrada R$130, três parcelas R$300,
total R$1030 e saldo final zero. Verifique arredondamento, datas e erros.
Crie duas organizações sintéticas em ambiente isolado e teste IDOR, acesso
cruzado por ID, sessão, papéis, exportação, IA e carteiras. Preserve flag
comercial desativada até evidências de isolamento e aceite. Sem cobrança real.

### 7. Gate de entrega
Registre revisão, testes, ambiente, horário, evidências, falhas P0/P1, decisão
e responsável. Atualize docs de aceite com SHA atual, não histórico. Entregue
manual operacional e pendências, sem prometer zero bugs. Separe aceite do
proprietário de liberação SaaS multiempresa.

## P1/P2 — após estabilizar entrega

Prepare staging privado em disco com competência imutável, processamento em
fluxo e checkpoints; dimensione custo e tempo. Reaproveite importadores,
manifesto de 270 células e preflight. Valide amostra AM, backup restaurado,
deduplicação, atualização de situação cadastral, supressão e idempotência.
Depois, expanda por UF com aprovação de recursos; atualizações mensais.
Não iniciar importação maciça nem ativar cron sem autorização.
Calibre pontuação de oportunidade com evidências reais e conversão; preserve
distinção fato/indício/hipótese. Priorize canais institucionais das empresas
com sinais comprováveis, em vez de enriquecimento indiscriminado.

## Como entregar cada etapa

Branch própria, PR pequeno, teste novo para regra nova, CI verde, descrição
de evidências e limitações. Atualizar CHANGELOG se houver comportamento novo
e esta fotografia quando a situação mudar. Nunca declarar implementação
equivalente a homologação, nem aprovação sem logs. Sem commits diretos na main.

## Decisão posterior do proprietário (25/11/2026)

Assistente IA fora da interface e da entrega atual. Esta decisão prevalece sobre as instruções históricas de geração real e de navegação pelo Assistente. Não reintroduzir o menu ou chamar provedor sem autorização. Priorizar contatos reais, Radar, Central, CRM e expansão dimensionada. Backend e histórico preservados.

### Bloqueio de CI após #212

O teste duplicado em backend/browser_tests/test_commercial_browser.py ainda esperava Assistente IA. Branch chatgpt/assistant-removal-browser-regression-213 ajusta a expectativa, sem restaurar o menu. Validar todos os workflows, depois merge pelo proprietário e deploy da revisão aprovada. Próximas prioridades: piloto institucional e diagnóstico de coletas parciais reais.

## Retomada de 26/11/2026 após #220

Consulte `docs/auditoria-retomada-2026-11-26.md`: #222 corrigiu descompressão e passou piloto externo 5/5, merge/implantação autorizados pelo proprietário. Produção fixada em 68d812124bb5fec26687361ee23d99865d8a089d, Railway SUCCESS. #223 trata integridade do Radar; #224 qualificação com origem e duplicatas globais. Nenhum lote produtivo, cron, gasto novo ou liberação comercial autorizado por essa decisão. Os gates de autenticação, piloto e cobertura continuam abertos.

## Retomada de 27/11: proteção das rotas individuais

Main confirmado em 43f9857fa101d70c3892fe6450e183beb0b4c23a (#223/#224 integrados com autorização). Último deploy comprovado em 26/11: Railway 82994a74-42e3-414d-b984-ffcd4faa0991, mesmo SHA; smoke anônimo final 29/29. A sessão autenticada foi restabelecida em 27/11. Assistente IA permanece removido.

Branch `codex/contact-eligibility-guards`: as rotas individuais de coleta e busca de domínio podiam contornar os critérios da fila. Agora reutilizam a validação de elegibilidade e revalidam cadastro/supressão após a consulta externa. Testes cobrem cadastro inativo/individual/incompleto, CNPJ inválido, concorrente, opt-out, duplicata fora da cidade e opt-out durante consulta. Validação local: compileall aprovado; 461 testes aprovados, 12 avisos de depreciação. A revisão inicial do PR #225 passou nos quatro workflows. A revisão final também verifica opt-out quando a consulta termina em erro; seu CI e merge ainda precisam ser confirmados. PR #226 expõe a atualização cadastral na ficha (431 testes locais, quatro workflows verdes; nove testes no navegador comercial). Sem migração ou ativação de serviços.

Piloto autorizado pelo proprietário: cinco CNPJs (Ágil, A M Consultoria, Albatroz, Mania Telecom e Converge), sem envio, API paga ou rotina recorrente. Em 26/11 foi criada apenas Ágil, ID 23359, CNPJ 18054044000160, razão social FELIPE LOPES FRANCO LTDA, ainda sem enriquecimento cadastral e sem coleta. Não duplicar. Em 27/11 foram cadastrados e confirmados pela UI os demais: A M Consultoria ID 23360, Albatroz ID 23361, Mania Telecom ID 23362 e Converge ID 23363. Os cinco ainda aguardam atualização cadastral e coleta. A interface não expõe o endpoint existente de atualização cadastral: corrigir antes de liberar a coleta. O piloto e a homologação integral continuam pendentes.
