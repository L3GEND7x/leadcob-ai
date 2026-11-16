# Compras.gov.br — contratos

Fonte oficial: API de Dados Abertos do Compras.gov.br, módulo Contratos.

## Estado

**Planejada.** O coletor existe e possui testes simulados, mas ainda não houve coleta real validada pelo LeadCob.

## Endpoint

`GET https://dadosabertos.compras.gov.br/modulo-contratos/1_consultarContratos`

O manual documenta, entre outros:
- `pagina` e `tamanhoPagina`;
- `codigoOrgao` obrigatório;
- `dataVigenciaInicialMin` e `dataVigenciaInicialMax` obrigatórios;
- retorno em `resultado`, com `totalRegistros`, `totalPaginas` e `paginasRestantes`.

O LeadCob lê objeto e informações complementares e aplica filtro textual/classificador de aderência.
O campo `niFornecedor` não é persistido porque a documentação admite CPF/CNPJ/Estrangeiro; o projeto
não deve incorporar CPF à prospecção.

## Limite operacional

Como o endpoint exige `codigoOrgao`, ele não é uma busca nacional livre por palavra-chave.
A descoberta nacional de órgãos/códigos precisa ser resolvida em etapa separada antes de automatizar cobertura ampla.

## Validação

- testes simulados: `backend/tests/test_compras_gov.py`;
- coleta real: **[NECESSÁRIO CONFERIR]** antes de promover a fonte para Integrada e testada.
