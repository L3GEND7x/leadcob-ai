# Changelog

## Não lançado
- **Backup Railway** (issue #31): o serviço de backup confere as credenciais antes do dump e para com mensagem
  clara (nome da variável, tamanho e tipo de problema, nunca o valor) se houver quebra de linha, caractere de
  controle, espaço, rótulo, token de sessão ou destino sem bucket. Registra as 4 etapas e o snapshot mais recente.
- Implantação Railway opcional: conexão PostgreSQL gerenciada, porta dinâmica e serviço diário de backup
  verificado e criptografado na Backblaze; mantém o Compose da VPS.
- Backup externo opcional: serviço Restic envia dumps locais verificados para armazenamento S3 compatível
  com criptografia, recusa dumps vencidos e verifica o repositório após cada envio.
- **Banco em produção** (issue #19): Alembic cria e versiona o esquema PostgreSQL antes de iniciar o painel;
  inicialização recusa versão ausente ou divergente. SQLite local mantém atualização legada.
- **Relatórios** (issue #18): tela e `GET /api/reports/summary` (`dias`, ou `inicio`/`fim`) com atividade, empresas
  contatadas, conversão (contato → resposta → reunião → proposta → contrato), entradas no funil, motivos de perda,
  sinais novos por fonte, empresas novas e tarefas. Exportação em `GET /api/reports/summary.csv`. Só contagens do que
  está registrado; sem projeções. Página publicada com os últimos 7 e 30 dias.
- Auditoria do CRM passa a registrar a hora original das ações reaplicadas na página publicada.

## Operação online — 10/11/2026
- Backup PostgreSQL agora só aparece com nome definitivo depois de `pg_dump` e `pg_restore --list` concluídos;
  uma falha preserva dumps anteriores e gera nova tentativa em uma hora.
- Teste em contêiner restaura um dump em banco separado e confere um registro criado pelo painel.
- A cópia criptografada fora da VPS continua pendente de provedor e credenciais próprios.

## 0.5.3 — 10/11/2026
- **Contatos institucionais na ficha**: lista com origem e status, confirmar/marcar inválido, cadastro manual com fonte
  obrigatória, link para pesquisar o site oficial (a confirmação é sua).
- **Busca de e-mails no site oficial** (`POST /api/contacts/discover/{id}`): lê só o site cadastrado na ficha e até 3
  páginas de contato do mesmo domínio, respeita robots.txt e guarda só caixas institucionais do próprio domínio
  (contato@, financeiro@...). E-mails de pessoas e de outros domínios são descartados. Tudo entra "a verificar".
- **Base do AM na página publicada**: `--seed-db` no gerador da página inclui empresas importadas da Receita.
- Página publicada com fichas completas para as 600 mais bem pontuadas e abordagens prontas para as 300 primeiras.

## 0.5.2 — 10/11/2026
### Etapa 2 (início) e integração da 0.5.1
- **Aba Contatos empresariais** (pacote 0.5.1, revisado e aprovado): canais institucionais por empresa, com origem, data,
  verificação e deduplicação; sincroniza só site e e-mail já presentes nas fichas; respeita a lista de supressão.
- **Identidade violeta** (decisão da usuária): preto profundo, violeta, branco e grafite em toda a interface; foco visível.
- **Gerador de abordagens** (`GET /api/companies/{id}/approach`): e-mail, WhatsApp, roteiro de ligação com objeções e
  7 follow-ups a partir dos fatos da ficha; hipóteses de setor marcadas; opt-out em todo texto; nunca afirma inadimplência;
  bloqueado para empresas suprimidas e concorrentes; para editais, só checklist (comunicação pelo edital).
- **Inteligência de cobrança** (`/api/portfolios`): importação de carteira (CSV) de cliente contratante, separada da
  prospecção; faixas A vencer, 1–7, 8–30, 31–60, 61–90, 91–180 e >180 dias com estratégia sugerida por faixa.
  Colunas com dados do devedor (nome, CPF, contatos, endereço) são descartadas na importação.
- **Laboratório de negociação** (`POST /api/negotiation/simulate`): correção, multa, juros (simples ou compostos),
  desconto, entrada e parcelamento (Price) só com premissas informadas pelo usuário; memória de cálculo.
- **Biblioteca de scripts** (`GET /api/scripts`, `config/scripts.json`): 14 modelos por categoria, com cuidados.
- Configurações: nome, empresa e contato para a assinatura das abordagens.
- Correção: a evidência da Inteligência do dia e a do gerador usam o mesmo sinal (mais forte e mais recente).

## 0.5.0 — 09/11/2026
### Etapa 1 do plano de evolução: operação diária, prospecção, qualificação e CRM
- **Central de comando** (`/api/command-center`): indicadores do dia, funil de 13 etapas, quem precisa de
  abordagem, follow-ups atrasados, maior pontuação, novos sinais, sinais recentes e tarefas.
- **Inteligência do dia** (`/api/daily-intelligence`): 5 empresas por regras explicáveis, com evidência,
  serviço sugerido, texto de abertura, canal, próxima ação e separação entre fatos, indícios e hipóteses.
- **Prospecção nacional** (`/api/companies/search`): filtros por região, UF, município, CNAE (principal e
  secundários), perfil, tipo de inadimplência, porte, situação, capital, anos de atividade, etapa, faixa e sinal.
- **Lead score explicável** (0–100, `docs/lead-score.md`): 8 componentes com motivo e natureza (fato,
  indício, hipótese); zerado para concorrentes, suprimidas e cadastros inativos.
- **CRM**: 13 etapas, ficha da empresa, histórico, interações (avançam a etapa), tarefas, próxima atividade,
  valor potencial informado, motivo de perda obrigatório, lista de supressão (opt-out), trava contra contato
  repetido e auditoria. Novas tabelas `interactions`, `tasks`, `suppressions`, `settings`; colunas novas em
  `companies` aplicadas automaticamente em bancos antigos.
- **Interface por módulos** (preto, vermelho escuro, branco e grafite), computador e celular.
- **Fontes** com cinco estados (inclui "Com erro de coleta" pela última captação e "Indisponível").
- **Exportação CSV** só com dados de PJ, sem empresas suprimidas.
- **Página publicada**: ações do CRM gravadas no banco da página (`crm_eventos`) e reaplicadas a cada
  atualização, com a hora original; oportunidades cadastradas na página viram sinais reais no banco.
### Correções
- Os 3 registros fictícios de demonstração não são mais criados em banco vazio (só com `DEMO_SEED=true`)
  e são removidos de bancos existentes, para não aparecerem como empresas reais.
- Perfil derivado do CNAE quando o banco antigo não o tinha (ex.: representantes comerciais).
- Dados embutidos na página publicada escapam `</`, evitando quebra do HTML.

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
| Catálogo de fontes | **Aproveitado e verificado** | Cada link testado; separado em integradas/consultadas/planejadas; compartilhamento público da Receita confirmado como espelho (mesmos ETags) |
| Exclusão de sócios/QSA | **Já adotado** | Ampliado: também sem e-mail/telefone (dados pessoais na amostra real) |
| `cnpj_import.py` (importar todos os ativos) | Não aproveitado | Gravaria dezenas de milhões de estabelecimentos (inclui filiais e MEIs) sem filtro de perfil; staging SQLite de todas as empresas; natureza e porte como códigos |
| Campos `cnae`, `porte`, `registry_status`, `legal_nature` | Não aproveitados | Já cobertos com mais informação (`cnae_main` + descrição, `company_size` por extenso, natureza por extenso) |
| `pncp.py` da v0.3 | Não aproveitado | Igual ao da v0.2: `tamanhoPagina=100` (HTTP 400 na API real) e sem classificação |
| `backend/leadcob.db` incluído no ZIP | Não aproveitado | Banco não deve ser versionado |

## 0.2.1 — 09/11/2026
- Conector PNCP corrigido e validado com dados reais (ver `docs/pncp-connector.md`).
