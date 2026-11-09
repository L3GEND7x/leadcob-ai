# Catálogo de fontes do LeadCob AI

Verificado em 2026-11-09. Fonte única: `config/sources.json` (também em `GET /api/sources`).

| Categoria | Significado |
|---|---|
| **integrada** | conectada ao sistema e testada com dados reais |
| **consultada** | documentação ou página de referência usada no desenvolvimento |
| **planejada** | possibilidade ainda NÃO conectada — não tratar como integração |

## Fontes integradas

| Fonte | Endereço | Oficial | Documentada | Uso | Situação |
|---|---|---|---|---|---|
| PNCP — índice de busca do portal | `https://pncp.gov.br/api/search/` | sim | não | Descoberta nacional de editais por termo | Validada em 09/11/2026; instável (respostas vazias intermitentes); resultado tratado como indício |
| PNCP — API de consulta | `https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}` | sim | sim | Confirmação do edital (objeto, prazo, valor, modalidade) e varredura por data | Validada em 09/11/2026; tamanhoPagina máximo aceito = 50 |
| Receita Federal — arquivos de dados abertos do CNPJ | `https://arquivos.receitafederal.gov.br/index.php/s/gn672Ad4CF8N6TK` | sim | sim | Base de empresas-alvo por CNAE/UF/porte (job mensal, leitura em fluxo por HTTP Range ou ZIPs locais) | Validada em 09/11/2026 (publicação 2026-10); espelho com os mesmos arquivos: https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9 |
| BrasilAPI — CNPJ | `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` | não (terceiro) | sim | Consulta individual de CNPJ (republica os dados abertos da Receita) | Validada em 09/11/2026; conferida com o importador (4/4 registros iguais) |
| Minha Receita — CNPJ | `https://minhareceita.org/{cnpj}` | não (terceiro) | sim | Reserva da BrasilAPI (mesmo esquema) | Validada em 09/11/2026 |
| Greenhouse — Job Board API | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs` | sim | sim | Vagas publicadas por empresa (board configurado) | Validada em 09/11/2026: 12 boards existentes (10 com vagas) entre 46 identificadores testados; ideia do conector veio do pacote v0.3 |
| Lever — Postings API | `https://api.lever.co/v0/postings/{site}` | sim | sim | Vagas publicadas por empresa (board configurado) | Validada em 09/11/2026: 2 boards existentes (1 com vagas) entre 31 identificadores testados |

## Fontes consultadas

| Referência | Endereço | Situação |
|---|---|---|
| Receita Federal — Dados abertos de cadastros | https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros | Página acessível em 09/11/2026 |
| Receita Federal — Repositório de dados abertos | https://www.gov.br/receitafederal/dados | Página acessível em 09/11/2026 |
| Receita Federal — Layout/metadados do CNPJ (PDF) | https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf | Conferido campo a campo com o importador em 09/11/2026 (Estabelecimentos 30 campos; Empresas 7) |
| dados.gov.br — Conjunto CNPJ | https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj | Página acessível em 09/11/2026 |
| Receita Federal — CNPJ alfanumérico | https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/cnpj-alfanumerico | Confirma IN RFB 2.229 (publicada em 15/10/2024) e atribuição a novas inscrições a partir de jul/2026; validação do DV implementada e testada com o exemplo 12.ABC.345/01DE-35 |
| PNCP — Swagger da API de consulta | https://pncp.gov.br/api/consulta/swagger-ui/index.html | Página acessível em 09/11/2026 |
| Greenhouse — documentação da Job Board API | https://docs.greenhouse.io/job-board | Página acessível em 09/11/2026 |
| Lever — documentação da Postings API | https://github.com/lever/postings-api | Não acessível deste ambiente (bloqueio de rede); endpoint validado diretamente |
| ANPD — Guia orientativo de legítimo interesse | https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_orientativo_hipoteses_legais_tratamento_de_dados_pessoais_legitimo_interesse | Página acessível em 09/11/2026 |
| LGPD — Lei 13.709/2018 | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm | Não respondeu deste ambiente em 09/11/2026 — conferir manualmente |

## Fontes planejadas (não conectadas)

| Fonte | Uso pretendido | Situação |
|---|---|---|
| DataJud (CNJ) — API pública de processos | Sinal de demanda: empresas autoras de muitas execuções/monitórias | NÃO conectada; endereço e termos de uso a verificar |
| Gupy — portal de vagas | Maior cobertura de vagas no Brasil | NÃO conectada; não há API pública documentada para busca; verificar termos antes de qualquer uso |
| Diários oficiais municipais | Licitações de municípios que não publicam no PNCP | NÃO conectada; fonte e termos a verificar |
| Sites institucionais das empresas | Contato institucional e sinais comerciais | Somente cadastro manual |

## Regras de uso

- Uma fonte só entra em **integrada** depois de testada com dados reais; a data fica registrada.
- Fontes de terceiros (BrasilAPI, Minha Receita) republicam dados da Receita: a fonte primária continua sendo a Receita Federal.
- Endpoints não documentados (índice de busca do PNCP) geram **indícios**, confirmados na API oficial antes de virar oportunidade comprovada.
- Dados de pessoas físicas (sócios/QSA, e-mail e telefone cadastrais) não são importados. Na amostra real de 09/11/2026, o e-mail cadastral trazia endereços pessoais de funcionários e contadores.
- Links recebidos com parâmetros de rastreamento (ex.: `utm_source`) são gravados sem eles.
