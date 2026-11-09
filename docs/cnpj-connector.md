# CNPJ — consulta individual e base de empresas-alvo

## 1. Consulta individual (tempo real)
`GET /api/cnpj/{cnpj}` (só consulta) e `POST /api/companies/{id}/enrich` (grava).
BrasilAPI → reserva Minha Receita (mesmo esquema). Ambas republicam os dados abertos
mensais da Receita: não é o cadastro em tempo real. Aceita CNPJ numérico e alfanumérico
(IN RFB 2.229/2024; atribuído a novas inscrições desde jul/2026).

## 2. Importação em lote (job mensal)
```bash
cd backend
# direto do compartilhamento da Receita (leitura em fluxo, sem baixar ~7 GB)
python -m app.jobs.import_cnpj --uf AM,PA --parts 0-9                      # todos os setores
python -m app.jobs.import_cnpj --segments varejo,atacado --uf AM --parts 0-9  # só alguns perfis
# a partir de ZIPs já baixados (pasta com Cnaes.zip, Municipios.zip, Naturezas.zip,
# Estabelecimentos*.zip e Empresas*.zip da MESMA competência)
python -m app.jobs.import_cnpj --local-dir ../data/cnpj --release 2026-10 --segments atacado
# teste rápido sem gravar
python -m app.jobs.import_cnpj --segments educacao_privada --parts 1 --limit 20 --dry-run
```
Perfis: `GET /api/segments` (`app/services/segments.py`). Desde a v0.4 são rótulos, não filtro:
toda empresa ativa recebe um perfil e os tipos de inadimplência típicos do setor (`GET /api/debt-types`).

### Empresário individual e MEI
Natureza 213-5. Na amostra real (3.000 empresas do arquivo Empresas0), 84% eram dessa natureza e 70% delas
tinham razão social = nome da pessoa + CPF. Por isso ficam fora por padrão. `--include-individual` inclui,
removendo o CPF do nome — o nome continua sendo dado pessoal: documente a base legal antes (LGPD).

### Volume
Todos os setores numa UF grande pode passar de centenas de milhares de empresas. O job para em
`--max-records` (padrão 300 mil) e pede para dividir por UF ou perfil.

### Como funciona
1. Lê `Estabelecimentos*.zip` e mantém: situação ATIVA, só matriz (`--include-branches` muda), UF e CNAE do perfil.
2. Completa razão social, porte, natureza e capital em `Empresas*.zip`. Esses arquivos são
   **particionados e ordenados por CNPJ básico** (verificado na publicação 2026-10): o job lê
   apenas os arquivos necessários e para ao passar do maior CNPJ procurado. Se a ordenação
   falhar, relê o arquivo inteiro — nenhum registro se perde em silêncio.
3. Traduz CNAE, município e natureza pelas tabelas oficiais (`Cnaes`, `Municipios`, `Naturezas`).

### Custos medidos (09/11/2026, via proxy)
- ~12.500 linhas/s, ~0,85 MB/s comprimidos.
- Publicação inteira de Estabelecimentos (~5,4 GB): ~1h45. Filtrar por UF não reduz a leitura.
- Etapa Empresas: de ~2 min (CNPJs antigos, arquivos 1–2) a ~11 min (CNPJs recentes, arquivo 0 com 570 MB).
- Em amostra de ~1 milhão de linhas: 68% baixadas, 13% ativas.

### Layout
Conferido campo a campo com o PDF oficial `cnpj-metadados.pdf` e com dados reais;
4 de 4 registros importados conferiram com a BrasilAPI (CNAE, município, UF, situação, matriz).

### O que NÃO é importado (LGPD)
Sócios/QSA, e-mail, telefones e endereço completo. Na amostra real, o e-mail cadastral
continha endereços pessoais de funcionários/contadores — não é canal institucional.

### Limite de interpretação
Estar no CNAE do perfil não comprova inadimplência, demanda ou capacidade de compra.
