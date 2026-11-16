# Conector Querido Diário

Fonte pública para busca em diários oficiais municipais.

## Estado

**Planejada.** O código do coletor e os testes simulados existem, mas a fonte não pode ser classificada como
"Integrada e testada" até uma coleta real funcionar no ambiente do LeadCob.

## Endpoint documentado

`GET https://api.queridodiario.ok.org.br/gazettes`

Parâmetros usados pelo LeadCob:
- `territory_ids`: códigos IBGE municipais separados por vírgula;
- `querystring`: termo pesquisado;
- `excerpt_size=500`;
- `number_of_excerpts=1`;
- `size` e `offset` para paginação.

A documentação pública informa resposta com `total_gazettes` e `gazettes`, incluindo município, UF,
data, URL do diário e excertos quando a busca textual é usada.

## Regra de segurança comercial

Um achado em diário oficial é **sinal a confirmar**, nunca prova de oportunidade comercial pronta.
O mesmo classificador de aderência usado pelo PNCP é aplicado ao excerto, mas a ausência de prazo e
estrutura de edital impede classificar automaticamente como oportunidade comprovada.

## Validação

- Testes simulados: implementados em `backend/tests/test_querido_diario.py`.
- Coleta real: **[NECESSÁRIO CONFERIR]**. O ambiente desta sessão não resolveu o domínio da API,
  portanto nenhum resultado real foi gravado nem usado para promover a fonte a integrada.
