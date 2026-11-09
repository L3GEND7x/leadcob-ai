# LeadCob AI — MVP 0.4.0

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

## API
- `GET /api/health`
- `GET /api/dashboard/summary` — inclui `proven` (oportunidades comprovadas) e `to_confirm` (sinais a confirmar)
- `GET /api/opportunities` (filtros `kind`, `status`, `signal`, `q`; descartados só com `status=discarded`)
- `POST /api/opportunities`
- `POST /api/agents/run/{id}`
- `POST /api/capture/pncp` (`mode=busca|varredura`, `only_open`, `include_review`, `max_pages`, `days`)
- `POST /api/capture/jobs` — vagas em boards Greenhouse/Lever configurados
- `GET /api/capture/runs`
- `GET /api/cnpj/{cnpj}` · `POST /api/companies/{id}/enrich`
- `GET /api/prospects` (filtros `segment`, `uf`, `cnae`, `size`, `min_capital`, `q`) · `GET /api/segments`
- `GET /api/sources` — catálogo (integradas, consultadas, planejadas)
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
Os três registros iniciais (vagas/terceirização) são exemplos demonstrativos.
Sem autenticação, HTTPS ou publicação em servidor: **não expor na internet**.

## Segurança antes de publicar na internet
Adicionar autenticação, HTTPS, gestão de segredos, backups, migrações, rate limiting, logs/monitoramento e política de
retenção. Respeitar termos de uso e controles técnicos das fontes. Priorizar dados de pessoa jurídica e canais
institucionais; não coletar CPF, dados financeiros privados, dados sensíveis ou contatos pessoais sem necessidade e base
legal documentada. Registrar fonte, URL, data e finalidade. Manter opt-out/lista de supressão. Campanhas externas em
escala exigem aprovação humana.
