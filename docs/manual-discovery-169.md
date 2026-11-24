# PR #169 — processamento manual da fila no plano atual Railway

**Contexto:** a Railway recusou a criação do novo serviço privado com a mensagem `Free plan resource provision limit exceeded`. Não houve worker adicional, e não foi realizado upgrade ou contratação.

Este PR permite executar **uma única empresa por clique**, dentro de um lote previamente criado pelo proprietário. É fallback manual, não worker contínuo.

- Rota `POST /api/contacts/discovery-jobs/{job_id}/process-one`, autenticada como proprietário e protegida por CSRF pelo middleware existente.
- Seleciona apenas itens do lote solicitado com a proteção transacional de claim token/lease existente; o bloqueio por processo evita duas requisições manuais simultâneas na mesma réplica. Entre réplicas, a claim do banco continua protegendo itens individuais.
- Respeita supressões globais, CNPJ válido, site empresarial cadastrado, filtro de DNS/SSRF, robots.txt, URLs de origem e canais não verificados. Não envia mensagens. Uma solicitação pode levar alguns segundos e sofrer timeout, registrando a tentativa na fila; não inventar sucesso.
- Registra um evento `discovery_manual_step` sem valores de contato ou CNPJ; retém resultados e origem nas tabelas existentes.
- Botão de confirmação no histórico de lotes, com atualização da fila e indicadores. Nenhuma execução automática e nenhuma nova despesa fixa de infraestrutura.

**Aceite**: testes HTTP com autenticação, CSRF, opt-out, isolamento do lote, apenas uma execução por clique, não repetição e canais `a_verificar`; CI e navegador. A execução com sites reais precisa de revisão e seleção do proprietário na interface. Pode haver bloqueio de saída de rede, latência ou recusa de robots.txt; medir antes de dimensionar um worker dedicado.

**Limitação**: a operação ocorre na requisição web, não possui processamento em segundo plano nem garantia de concluir caso haja interrupção de rede/container. Para operação em escala, contratar recursos extras ou infraestrutura separada somente após avaliação de custo e viabilidade.
