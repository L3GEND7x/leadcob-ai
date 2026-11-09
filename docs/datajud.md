# DataJud (CNJ) — mapa de inadimplência judicializada

`POST /api/market/datajud?uf=AM&months=12` consulta e guarda uma fotografia; `GET` devolve a última.
No painel: seção "Mapa de inadimplência judicializada".

## O que mede
Processos de cobrança ajuizados na Justiça Estadual da UF, por:
- **classe** (códigos conferidos na própria API em 09/11/2026): 12154 Execução de Título Extrajudicial,
  40 Monitória, 81 Busca e Apreensão em Alienação Fiduciária, 93 Despejo por Falta de Pagamento,
  94 Despejo por Falta de Pagamento Cumulado com Cobrança, 1116 Execução Fiscal;
- **tipo de inadimplência**: assuntos agrupados em tipos (`app/services/segments.py`, `DEBT_TYPES`),
  cada assunto em um único tipo; genéricos ("Pagamento", "Compra e Venda"...) ficam como não classificados;
  dívida ativa vem da classe Execução Fiscal;
- **município** (nome via BrasilAPI/IBGE).

Exemplo real (TJAM, 01/11/2025 a 09/11/2026): 29.566 processos; financiamentos com garantia 12.347;
notas promissórias 2.988; dívida ativa 2.806; crédito bancário 2.692; aluguéis/condomínios 1.523;
Manaus concentra 24.685.

## O que NÃO faz
- **Não identifica empresas.** A API pública resguarda "dados de partes" (documentação oficial). Serve
  para escolher regiões e setores, não para gerar lista de leads. Identificar quem cobra exige outra fonte
  (ver "planejadas" em `docs/fontes.md`).
- Só Justiça Estadual (TJ). Justiça Federal (execuções fiscais federais, CEF) não entra.
- Somas por assunto não são exclusivas: um processo pode ter vários assuntos.

## Operação
- Endereços dos 27 tribunais estaduais conferidos em 09/11/2026: `api_publica_tj{uf}`, com DF = `tjdft`.
- Chave: pública, publicada pelo CNJ em https://datajud-wiki.cnj.jus.br/api-publica/acesso — pode mudar.
  Em HTTP 401/403, atualize `DATAJUD_API_KEY`.
- A fila de buscas do CNJ devolve HTTP 429 com frequência (observado em 09/11/2026): o conector tenta de novo
  com espera crescente. Uma consulta de UF leva de 10 s a 2 min.
- Termo de uso: **[NECESSÁRIO CONFERIR]** — a página não pôde ser lida deste ambiente.
