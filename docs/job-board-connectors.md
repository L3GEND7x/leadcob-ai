# Vagas — Greenhouse e Lever

Ideia original: pacote LeadCob v0.3. Revisado com 928 vagas reais (09/11/2026).

## Configuração
`config/job_boards.json` (boards verificados) e/ou `JOB_BOARD_SOURCES_JSON` no `.env`
(formato da v0.3: `[{"provider":"greenhouse","token":"...","company_name":"...","cnpj":"..."}]`).
Preencha `cnpj` só com CNPJ conferido — com ele o LeadCob consulta o CNAE e marca
**concorrentes** (CNAE 8291-1/00, atividades de cobrança).

## Captura
`POST /api/capture/jobs` (botão "Buscar vagas públicas").

| Regra | Motivo (dados reais) |
|---|---|
| Classifica pelo **título** | 36 de 45 acertos por descrição eram ruído (ex.: "Gerente de Relacionamento") |
| Exclui "analista de crédito"/"credit analyst" sem termo de cobrança | concessão de crédito ≠ cobrança |
| Não usa "recovery"/"collection" isolados | casam com "Disaster Recovery" e "data collection" |
| Desescapa o HTML do Greenhouse antes de limpar | o campo `content` vem como `&lt;p&gt;` |
| Pagina o Lever (`skip`/`limit`) | a v0.3 lia só as 100 primeiras |
| Vaga que some de um board lido com sucesso → `vaga_encerrada` | histórico preservado |
| Vaga fora do Brasil → `revisar` | |

Leitura comercial: `operacao_interna` (equipe própria — argumento: terceirizar/complementar)
ou `estrategia_dados` (área estruturada — em geral já usa assessorias; argumento: credenciamento).
Vaga é sinal de contratação interna, **não** prova de intenção de terceirizar.

## Cobertura real
De 46 (Greenhouse) e 31 (Lever) identificadores de empresas brasileiras testados, 12 e 2
existiam — quase todos bancos e fintechs. Resultado da primeira captura: 775 vagas lidas,
7 aderentes (C6 Bank, Inter, QuintoAndar, Neon). A maior parte dos empregadores brasileiros
(inclusive o público típico de cobrança: atacado, indústria, educação) usa outras plataformas.
