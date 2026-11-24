# PR #177 — oportunidades de pesquisa com regras coerentes

## Divergência observada
O relatório \`contactability\` (PR #173) considerava somente CNPJs empresariais ativos, removia duplicatas e opt-outs, excluía e-mails nominais e verificava a validade do canal. Já \`discovery-targets\` incluía empresários individuais e considerava qualquer string não vazia como contato existente, inclusive e-mails pessoais ou URLs inválidas. Assim, o relatório e a fila de pesquisa podiam mostrar números diferentes e oferecer empresas que não deveriam entrar na prospecção.

## Correção
- Reutilização dos critérios de natureza jurídica, canal institucional, URL de fonte e supressão CNPJ-global já usados no painel.
- Os CNPJs com status cadastral local contraditório, baixado ou sem informação ficam fora da lista de descoberta; nenhuma alteração do cadastro é feita.
- Mantidos os dois totais: \`active_unique_cnpjs\` (todos os CNPJs válidos ativos, inclusive individuais) e \`active_corporate_cnpjs\` (grupo empresarial elegível), para deixar explícito o denominador dos percentuais e das oportunidades.
- \`with_channel\`, \`with_verified_channel\`, \`with_verified_sourced_channel\`, \`missing_channel\` e \`ready_for_site_discovery\` são apurados sobre a população empresarial elegível e contatos do canal escolhido. Um e-mail nominal NÃO suprime uma empresa da lista de candidatos que ainda precisam de caixa institucional.
- Para marcar um site como pronto para revisão, URL cadastrada deve ser pública em formato válido e sem conflito entre as fichas. Um domínio local, porta proibida ou URL malformada não pode ser candidato.
- A seleção permanece manual, sem iniciar worker, scraping, disparos ou cobranças. O proprietário deve conferir titularidade e origem antes de criar lote.

## Aceite e limites
Testes sintéticos com divergência cadastral, opt-out por ID de duplicata, empresário individual, e-mail pessoal, site interno/invalidado e empresa com e-mail funcional. Testes comparativos verificam igualdade entre os números dos canais \`email\`, \`phone\` e \`linkedin\` nos dois endpoints, além da visibilidade no navegador desktop/mobile.

Nenhuma contagem real de Manaus é afirmada. O status "verificado" é dado interno, não prova autorização de contato nem interesse comercial. A leitura do banco é local, sem integração adicional e sem custo externo.


## Benchmark PostgreSQL sintético
A massa do teste de 53.000 CNPJs agora informa a natureza jurídica empresarial, pois o cenário de performance mede a consulta de empresas elegíveis. Isto muda a composição da massa sintética, não as métricas de empresas reais nem resultados financeiros. O benchmark segue com mesma quantidade de CNPJs e contatos, armazenamento isolado e limpeza da schema temporária; números de tempo anteriores podem não ser diretamente comparáveis após a alteração da regra de filtragem.
