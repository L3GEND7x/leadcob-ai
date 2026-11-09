# Changelog

## 0.4.0 — 09/11/2026
### Todos os setores, todos os tipos de inadimplência
- Base de empresas-alvo deixa de filtrar por 8 perfis: **toda empresa ativa de qualquer setor e porte** entra
  (do pequeno varejista ao grande grupo). Os perfis viram rótulos de priorização, com o tipo de inadimplência
  típico de cada setor; toda divisão da CNAE (01–96) tem perfil (teste garante). Excluídas só as divisões 97
  (empregador doméstico) e 99 (organismos internacionais).
- Varejo, construção, veículos, transporte, serviços, setor público, associações etc. passam a ter perfil próprio.
- Empresário individual/MEI (natureza 213-5) fica fora por padrão: na amostra real, 70% das razões sociais
  eram nome + CPF. `--include-individual` inclui com o CPF removido (decisão de base legal do usuário).
- Limite de segurança `--max-records` (padrão 300 mil) para importações grandes: dividir por UF.
### DataJud (CNJ)
- Mapa de inadimplência judicializada por UF: classes de cobrança, tipos de dívida e municípios.
  Não identifica empresas (a API pública não traz partes). Ver `docs/datajud.md`.

## 0.3.1 — 09/11/2026
- Perfil "atacado" passa a usar CNAE 46.2 a 46.9. O grupo 46.1 (representantes comerciais e
  agentes do comércio) saiu: trabalham por comissão e não têm carteira própria. Na primeira
  importação real (15 empresas), eram 4 de 13 do perfil.
- Cada importação reavalia o perfil das empresas já gravadas, de modo que uma mudança de regra
  também limpa registros antigos.
- Painel: porte e capital em linhas separadas na tabela de empresas-alvo.
- Primeira importação real gravada: 15 de 15 razões sociais completadas em 987 s, sendo 846 s
  gastos no arquivo Empresas0 (570 MB) para completar apenas 2 empresas de CNPJ recente.

## 0.3.0 — 09/11/2026
### CNPJ (Receita Federal)
- Consulta individual (BrasilAPI → Minha Receita), validação de CNPJ alfanumérico.
- Importador em lote por HTTP Range direto do compartilhamento da Receita, ou de ZIPs locais.
- Base de empresas-alvo com perfis por CNAE e filtros (perfil, UF, CNAE, porte, capital).
### Vagas
- Conectores Greenhouse e Lever, classificação pelo título, detecção de concorrentes e de vagas encerradas.
### Catálogo de fontes
- `config/sources.json` + `docs/fontes.md` + `GET /api/sources`: integradas, consultadas e planejadas.

### Aproveitamento do pacote v0.3 recebido em 09/11/2026
| Item do pacote | Decisão | Motivo |
|---|---|---|
| Conector Greenhouse/Lever | **Aproveitado e revisado** | Ideia correta (APIs públicas documentadas). Corrigidos com dados reais: filtro por descrição (80% ruído), "analista de crédito" como falso positivo, HTML escapado, falta de paginação no Lever, empresa duplicada por vaga sem CNPJ |
| `JOB_BOARD_SOURCES_JSON` | **Aproveitado** | Mantido compatível, somado ao arquivo `config/job_boards.json` |
| Importação de ZIPs locais | **Aproveitado** (`--local-dir`) | Útil sem internet ou para reprocessar uma competência |
| Catálogo de fontes | **Aproveitado e verificado** | Cada link testado; separado em integradas/consultadas/planejadas; link do compartilhamento `YggdBLfdninEJX9` confirmado como espelho (mesmos ETags) |
| Exclusão de sócios/QSA | **Já adotado** | Ampliado: também sem e-mail/telefone (dados pessoais na amostra real) |
| `cnpj_import.py` (importar todos os ativos) | Não aproveitado | Gravaria dezenas de milhões de estabelecimentos (inclui filiais e MEIs) sem filtro de perfil; staging SQLite de todas as empresas; natureza e porte como códigos |
| Campos `cnae`, `porte`, `registry_status`, `legal_nature` | Não aproveitados | Já cobertos com mais informação (`cnae_main` + descrição, `company_size` por extenso, natureza por extenso) |
| `pncp.py` da v0.3 | Não aproveitado | Igual ao da v0.2: `tamanhoPagina=100` (HTTP 400 na API real) e sem classificação |
| `backend/leadcob.db` incluído no ZIP | Não aproveitado | Banco não deve ser versionado |

## 0.2.1 — 09/11/2026
- Conector PNCP corrigido e validado com dados reais (ver `docs/pncp-connector.md`).
