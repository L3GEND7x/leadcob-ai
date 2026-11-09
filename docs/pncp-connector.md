# Conector PNCP — v0.2.1

## Fluxo

1. **Descoberta** — `GET https://pncp.gov.br/api/search/` (índice de busca usado pelo próprio portal),
   com busca exata de cada termo, `tipos_documento=edital`, `status=recebendo_proposta` (padrão) ou `todos`.
   - **Atenção:** este endpoint **não** consta do manual da API de consulta. Pode mudar ou ser bloqueado sem aviso.
     Por isso o resultado dele é tratado apenas como **indício**.
2. **Classificação de aderência** (`app/services/procurement.py`) sobre o objeto da contratação:
   `alta` (cobrança propriamente dita) · `revisar` (tributário/previdenciário ou menção indireta) · `descartar`.
3. **Confirmação** — para o que não foi descartado: `GET /api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`
   (API oficial de consulta). Traz objeto, prazo de propostas, valor estimado, modalidade e link do sistema de origem.
4. **Natureza**: `edital_aberto` · `edital_encerrado` · `contratacao_direta` (inexigibilidade/dispensa) · `prazo_nao_informado`.

**Oportunidade comprovada** = edital aberto + aderência alta + confirmação na API oficial.
Todo o resto é **sinal a confirmar**. Em ambos os casos `status=review` e `is_verified=false`: a leitura humana do
edital (habilitação, qualificação técnica, remuneração, prazo) continua obrigatória.

Itens descartados não entram no painel; amostras com o motivo voltam na resposta da captação para auditoria do filtro.
Se uma regra mudar e um registro já gravado passar a "descartar", ele recebe `status=discarded` (consultável pelo filtro).

## Modo de contingência: `varredura`

`POST /api/capture/pncp?mode=varredura&days=14&max_pages=3` usa o endpoint documentado
`GET /api/consulta/v1/contratacoes/publicacao` por data e modalidade (4, 6, 8, 9, 10, 12), com filtro textual local.

## Validação com a API real (09/11/2026)

| Verificação | Resultado |
|---|---|
| `/contratacoes/publicacao` com `tamanhoPagina=100` (valor da v0.2) | **HTTP 400 "Tamanho de página inválido"** → toda captação da v0.2 falharia. Corrigido para 50. |
| Volume publicado em 14 dias, 6 modalidades | 50.902 registros (só pregão eletrônico: 13.977 / 280 páginas) |
| Varredura com 3 páginas por modalidade | 800 registros lidos (1,6%) → **0 oportunidades**. Não serve como motor nacional. |
| Busca + confirmação (1ª execução) | 70 encontrados → 67 descartados → 3 gravados (2 eram falso positivo, ver abaixo) |
| Busca + confirmação (após ajuste) | DesenvolveSP — credenciamento de cobrança extrajudicial: **comprovada**; Colinas/RS — credenciamento de cobrança de tributos: **sinal a confirmar**; SAMAE/SC — leitura de hidrômetros: **descartado** |
| Estabilidade do índice de busca | Respostas vazias intermitentes (~30% das consultas em algumas execuções) e recusa temporária após rajadas. Há retentativa com espera; termos que falham ficam registrados e a execução fica `partial`. |

Falsos positivos reais que orientaram as regras: cobrança de pedágio/TAGs, decoração natalina, credenciamento de
instituições financeiras para arrecadação, cartórios (protesto), serviços gráficos de faturas, leitura de hidrômetros
com "avisos de inadimplência", software de gestão. Achado de mercado: a maior parte das contratações com
"recuperação de crédito" é de **assessoria para recuperação de créditos tributários/previdenciários de municípios**
(frequentemente inexigibilidade para escritórios de advocacia) — segmento diferente de cobrança de carteira.

## Limites conhecidos

- A captação roda de forma síncrona na requisição (1–3 min). Para produção: fila/worker (Redis já previsto no compose).
- As listas de termos são heurísticas calibradas com poucos casos reais; revisar com o histórico de descartes.
- O conector não lê anexos/PDF do edital; a decisão de participar depende dessa leitura.
- APIs de manutenção do PNCP (envio de dados) são outra categoria e exigem credenciamento; o LeadCob só consulta.
