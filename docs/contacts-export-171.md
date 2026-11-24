# Exportação institucional por UF e município — #171

O dono autenticado pode exportar **até 5.000 registros por solicitação**, com offset até 100.000, em CSV UTF-8 com BOM, delimitador ponto e vírgula. Default: **somente canais verificados**, UF AM, município Manaus. Incluir canais `a_verificar` exige ação consciente na interface e origem URL registrada para esses contatos. Campos: CNPJ, razão social, UF, município, canal, valor, situação de verificação, fonte, URL de origem e data de conferência. Download depende da sessão do proprietário. Sem canal de assinantes, sem escrita no banco, sem uso de WhatsApp, OpenAI ou serviço externo.

**Filtros:** CNPJ validado, situação cadastral ATIVA, natureza jurídica empresarial identificada (exclui empresarial individual e sem classificação), supressão global de ID ou CNPJ (inclusive duplicatas), exclusão de valores vazios/anonimizados, e-mails só de caixas institucionais conhecidas, deduplicação por CNPJ+canal+valor por página. Proteção contra CSV/Excel Formula Injection em todas as colunas e quebra de linha incorporada.

**Limites:** O status `verificado` é o controle de revisão do sistema e não comprova a natureza jurídica do contato, titularidade do telefone, consentimento ou base legal para mensagens. Contatos pessoais que tenham sido erroneamente classificados como institucionais podem exigir revisão adicional antes da exportação. Os resultados são dados internos locais; não é censo do mercado. Paginação ocorre antes de filtros Python de supressão e deduplicação, portanto páginas podem ter menos de 5.000 linhas, e duplicações podem atravessar páginas; unir e conferir antes de utilizar. Não usar arquivos exportados para spam.

**Homologação:** teste HTTP com sessão e bloqueio sem autenticação, caracteres maliciosos, situação cadastral, opt-out, limite e canais não verificados. CI e navegador devem passar antes da implantação. Nenhum contato real precisa ser mostrado em logs ou testes sintéticos.


## Correção de paginação e rastreabilidade — PR #172
O offset passa a representar **contatos elegíveis únicos depois dos filtros de CNPJ, situação, supressão, natureza jurídica, origem e caixa institucional**, não uma posição arbitrária nas linhas brutas do banco. A página seguinte é indicada pelo cabeçalho \`X-Has-More\` e \`X-Next-Offset\`, e só é obtida mediante novo clique explícito; a página atual permanece um CSV independente. Duplicatas por CNPJ+tipo+contato são descartadas através de todas as páginas; na presença de registros equivalentes prioriza-se o \`verificado\`. A consulta usa iteração em lotes para limitar memória do processo.

A consistência entre diferentes downloads presume que os dados não mudaram entre as consultas. Se foram inseridos/alterados contatos ou regras de supressão, refaça a exportação desde o início para evitar saltos. Não há snapshot histórico nem garantia de completude de contatos fora da base local.


## PR #176 — consistência de situação cadastral antes de exportar

O exportador verifica todos os registros do **mesmo município** e não exporta os canais de um CNPJ se qualquer registro duplicado estiver marcado como `BAIXADA`, `SUSPENSA`, `INAPTA` ou tiver situação desconhecida — ainda que outro registro pareça `ATIVA`. Esse cuidado evita transformar uma divergência da base local em um lead aparentemente ativo. Os arquivos não exibem informações dessas empresas em quarentena. O filtro executa somente uma consulta de leitura adicional, iterada em lotes, e preserva a paginação de contatos elegíveis do #172.

A divergência é detectada dentro do município solicitado; divergências entre municípios ou fontes externas ainda exigem reconciliação da base. A situação cadastral armazenada não confirma a atualização real na Receita Federal. Nenhuma coleta externa ou alteração de registros foi feita.
