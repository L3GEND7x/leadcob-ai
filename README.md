# LeadCob AI — MVP 0.2.1

Plataforma individual de inteligência comercial B2B para identificar (1) empresas com vagas de cobrança/contas a
receber, (2) empresas com sinais que possam indicar demanda por recuperação de crédito terceirizada e (3) editais
públicos de serviços de cobrança. Cobertura pretendida: Brasil.

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
- `GET /api/capture/runs`
- `GET /api/sources`

## Estado real desta entrega
- **PNCP: conectado e validado com dados reais em 09/11/2026** (ver `docs/pncp-connector.md`). Separa
  *oportunidade comprovada* (edital aberto + objeto de cobrança + confirmação na API oficial) de *sinal a confirmar*.
  A descoberta depende de um endpoint de busca do portal que não é documentado oficialmente e é instável.
- Vagas, CNPJ (Receita Federal) e sites institucionais: **ainda não conectados**.
- Os três registros iniciais (vagas/terceirização) são exemplos demonstrativos, não leads reais.
- Sem autenticação, HTTPS ou publicação em servidor: **não expor na internet** nesta versão.

## Segurança antes de publicar na internet
Adicionar autenticação, HTTPS, gestão de segredos, backups, migrações, rate limiting, logs/monitoramento e política de
retenção. Respeitar termos de uso e controles técnicos das fontes. Priorizar dados de pessoa jurídica e canais
institucionais; não coletar CPF, dados financeiros privados, dados sensíveis ou contatos pessoais sem necessidade e base
legal documentada. Registrar fonte, URL, data e finalidade. Manter opt-out/lista de supressão. Campanhas externas em
escala exigem aprovação humana.
