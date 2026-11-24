# Expansão nacional — importação cadastral controlada

Objetivo: abranger as 27 UFs, todos os portes e perfis elegíveis, incluindo filiais.
O CNPJ identifica um estabelecimento; matriz e filial têm CNPJs distintos.
A base cadastral é potencial comercial, não prova de inadimplência ou de demanda.
Setor público e concorrentes devem permanecer em tratamento próprio. Não importar
MEI/empresário individual, dados de sócios, e-mails/telefones cadastrais ou CPF.

## Primeira etapa (este PR)
O comando novo usa o coletor existente da Receita com competência explícita,
uma UF e uma partição Estabelecimentos por execução. Todos os portes (inclusive
porte não informado), todos os CNAEs elegíveis e filiais; nenhuma publicação de
JSON empresarial em ramo público. A simulação não abre o banco nem grava registros.

```sh
cd backend
python -m app.jobs.import_national_registry --uf AM --part 0 --release AAAA-MM
```

Troque AAAA-MM pela competência oficial conferida; não misture ZIPs de meses distintos.
Opcional: --local-dir /caminho/privado/dados com todos os ZIPs da mesma competência.
Depois de backup restaurável, aprovação, revisão da amostra e janela de escritor
único (suspender demais importadores e cadastros concorrentes), acrescente --apply.
O modo apply exige a revisão Alembic correta; insere somente ausentes e preserva CRM,
contatos e fichas existentes. Respeita supressões por CNPJ e por registro associado.
Lotes de 500 em transações separadas; uma falha pode deixar lotes anteriores gravados,
e a repetição não duplica registros canônicos sob escritor único. Não há garantia
contra escrita concorrente por outros processos, nem atualização de empresas já
existentes, nem marcação de baixadas. Auditar CNPJs legados antes da expansão.

Limite de memória: 150 mil candidatos por execução, configurável até 300 mil.
Se exceder, falhar sem importar e subdividir com --municipality-code 0255 (exemplo:
Manaus; usar código da tabela Municipios.zip, não IBGE). Se a subdivisão ainda
exceder o limite, preparar staging em disco; não simplesmente aumentar o limite.
Se layout, DV ou identidade jurídica divergirem, o modo estrito recusa a partição.
Os contadores são relativos ao lote. coverage_complete é sempre false; não significa
cobertura oficial nem que todos os arquivos Empresas tenham sido processados.
A execução não valida externamente a titularidade de nenhum contato.

## Ordem proposta
1. AM (piloto), depois PA, RR, RO, AC, AP, TO.
2. Nordeste: MA, PI, CE, RN, PB, PE, AL, SE, BA.
3. Centro-Oeste: MT, MS, GO, DF.
4. Sudeste: MG, ES, RJ, SP.
5. Sul: PR, SC, RS.

Para cada competência, 27 UFs x 10 partições = 270 células lógicas. Registrar
status, competência, volume elegível, inseridos, existentes, suprimidos,
falhas e comparação com contagem de referência. Não tratar uma célula interrompida
como concluída. O processo atual exige uma execução por célula e não tem scheduler.

## Próximos marcos (não implementados neste PR)
- Manifesto persistente por competência/UF/partição com checkpoint e retry.
- Staging privado em disco para ler cada ZIP uma vez e suportar UFs grandes.
- Benchmark de armazenamento, consulta e custo em PostgreSQL isolado.
- Chave única/coordenação de importações e atualização cadastral auditada,
  inclusive situações inativas, preservando CRM e supressões.
- Enriquecimento institucional gradual apenas para empresas prioritárias, com
  fonte, data, revisão humana e opt-out, sem mensagens automáticas.
- Atualização mensal após validar competência, cobertura e orçamento.

Nenhuma expansão nacional real ou serviço adicional foi ativado neste PR.
