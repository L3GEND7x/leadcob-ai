# Pré-dimensionamento nacional

Antes da importação, execute uma leitura de cada arquivo Estabelecimentos para
estimar o tamanho das 27 UFs e municípios. O módulo não acessa o banco, não
grava empresas e não lê os ZIPs Empresas.

```sh
cd backend
python -m app.jobs.national_registry_preflight --release AAAA-MM --part 0 --local-dir /dados/privados
```

Use a competência oficial conferida e repita para partições 0–9. Sem --local-dir,
usa o coletor remoto já existente. --max-records deve corresponder ao importador.
A saída JSON permite decidir se uma UF inteira cabe no limite ou se precisa de
subdivisão municipal. Uma única leitura por partição dimensiona todas as UFs;
não equivale a importar todas as UFs. Os contadores são de linhas, antes de
deduplicação e exclusão de empresários individuais, não CNPJs elegíveis.
A verificação de natureza jurídica e supressões permanece no importador.

Layout, CNPJ inválido ou UF desconhecida são reportados e o comando termina
com erro para revisão. UF estrangeira ou formato novo da Receita pode exigir
tratamento específico. Códigos municipais ausentes são agregados como unknown,
não devem ser usados automaticamente para planejar sublotes.

Limitações: ainda não gera manifesto de subdivisões, nem staging em disco, nem
reduz as leituras do importador existente. Não publica dados pessoais ou
resultados automaticamente. Não executar 10 downloads simultâneos sem medir
rede, armazenamento, tempo e custo.
