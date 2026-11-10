# LeadCob AI — 0.5.3

Plataforma individual de inteligência comercial para captar **qualquer empresa que tenha inadimplentes** —
de qualquer setor e porte, do pequeno varejista ao grande grupo — e **todos os tipos de inadimplência**
(B2B, crediário, financiamentos, mensalidades, aluguéis e condomínios, serviços, faturas de consumo, dívida ativa).
Frentes: (1) empresas contratando para cobrança, (2) potenciais clientes de terceirização, (3) editais públicos.
Cobertura: Brasil.

## Executar

**Docker (recomendado):** copie `.env.example` para `.env` (`cp .env.example .env`; no PowerShell,
`Copy-Item .env.example .env`) e execute `docker compose up --build`. Abra http://localhost:8000 (dashboard) e
http://localhost:8000/docs (API).

**Local:** Python 3.11+, `pip install -r backend/requirements.txt` e `uvicorn app.main:app --app-dir backend --reload`.
Sem `DATABASE_URL`, usa SQLite local. Bancos criados em versões anteriores são atualizados no startup.

**Testes:** `cd backend && pip install pytest && python -m pytest`.

**Online (VPS):** configuração para um proprietário, com login, HTTPS, PostgreSQL e backup local diário:
consulte [operação online](docs/operacao-online.md). Exige domínio, VPS, senha e configuração própria.
O assistente OpenAI exige chave de API e teto mensal configurados no servidor.

## Módulos (0.5.2)
Central de comando · Inteligência do dia · Encontrar empresas · Sinais e oportunidades · CRM comercial (ficha,
histórico, tarefas, supressão, abordagem sugerida) · Contatos empresariais · Inteligência de cobrança · Laboratório de
negociação · Biblioteca de scripts · Radar de mercado · Fontes de dados · Configurações.
Rotina sugerida: `docs/manual-uso-diario.md`. Pontuação: `docs/lead-score.md`. O que está pronto e o que falta:
`docs/status-v0.5.md`.

## API
- `GET /api/health`
- `GET /api/command-center` — indicadores, funil e listas de trabalho do dia
- `GET /api/daily-intelligence?limit=5` — empresas do dia com evidência, serviço sugerido e próxima ação
- `GET /api/companies/search` — busca nacional (`q`, `region`, `uf`, `municipio`, `cnae`, `profile`, `debt_type`, `size`,
  `situacao`, `capital_min/max`, `years_min/max`, `stage`, `band`, `has_signal`, `sort`, `page`, `per_page`) · `GET /api/regions`
- `POST /api/companies` · `GET|PATCH /api/companies/{id}` (ficha: etapa, próxima atividade, valor potencial, notas)
- `POST /api/companies/{id}/interactions` · `POST /api/companies/{id}/tasks` · `GET /api/tasks` · `PATCH /api/tasks/{id}`
- `GET /api/pipeline` · `GET|POST /api/suppression` · `DELETE /api/suppression/{id}` · `GET|PUT /api/settings`
- `GET /api/companies/{id}/approach` · `GET|POST /api/portfolios` · `GET|DELETE /api/portfolios/{id}` · `POST /api/negotiation/simulate` · `GET /api/scripts`
- `GET|POST /api/contacts` · `POST /api/contacts/sync` · `POST /api/contacts/discover/{id}` · `PATCH /api/contacts/{id}/verify`
- `GET /api/export/companies.csv` — só dados de PJ, sem empresas suprimidas
- `GET /api/dashboard/summary` · `GET|POST /api/opportunities` · `POST /api/agents/run/{id}`
- `POST /api/capture/pncp` (`mode=busca|varredura`, `only_open`, `include_review`, `max_pages`, `days`) · `POST /api/capture/jobs` · `GET /api/capture/runs`
- `GET /api/cnpj/{cnpj}` · `POST /api/companies/{id}/enrich` · `GET /api/prospects` · `GET /api/segments`
- `GET /api/sources` — catálogo com estado de cada fonte
- `POST|GET /api/market/datajud?uf=AM` — mapa de inadimplência judicializada · `GET /api/debt-types`

## Estado real desta entrega
| Frente | Fonte | Situação (09/11/2026) |
|---|---|---|
| Editais públicos | PNCP | Integrada e validada com dados reais (`docs/pncp-connector.md`) |
| Vagas de cobrança | Greenhouse / Lever | Integrada e validada; cobertura limitada a quem usa essas plataformas (`docs/job-board-connectors.md`) |
| Base de empresas-alvo (todos os setores) | Receita Federal (dados abertos) + BrasilAPI | Integrada e validada; job em lote (`docs/cnpj-connector.md`) |
| Mapa de inadimplência por UF e tipo | DataJud (CNJ) | Integrada e validada; não identifica empresas (`docs/datajud.md`) |
| Sinais de terceirização | — | **Não há fonte que comprove demanda**: cadastro e vagas são indícios; exige contato direto |

Catálogo completo de fontes: `docs/fontes.md`. Histórico e decisões: `CHANGELOG.md`.
Nenhum dado fictício é criado (os exemplos de demonstração só existem com `DEMO_SEED=true`).
O acesso local sem senha é limitado ao próprio computador; para publicar use a configuração de produção.
Esta versão ainda não foi implantada em nuvem nem testada com credenciais reais de OpenAI ou Brave.

## Segurança e operação
Login individual e proteção CSRF, HTTPS na configuração de VPS, limite de tentativas de login e backup local estão implementados.
Antes de usar dados reais continuamente, implante migrações versionadas, cópia de backup fora da VPS, teste de restauração,
monitoramento e retenção documentada. Capturas externas ainda são síncronas; precisam de fila de trabalhos e agendamento para operação contínua.
Respeitar termos de uso e controles técnicos das fontes. Priorizar dados de pessoa jurídica e canais
institucionais; não coletar CPF, dados financeiros privados, dados sensíveis ou contatos pessoais sem necessidade e base
legal documentada. Registrar fonte, URL, data e finalidade. Manter opt-out/lista de supressão. Campanhas externas em
escala exigem aprovação humana.

## Contatos empresariais (v0.5.1, complemento)
A nova aba Contatos sincroniza canais institucionais existentes nas fichas, permite cadastro via API com fonte e revisão de status. Não coleta dados pessoais nem promete localizar contatos inexistentes. Consulte `docs/contatos.md`.
