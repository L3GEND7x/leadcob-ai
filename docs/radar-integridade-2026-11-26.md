# Radar — integridade da captura PNCP e operação diária

Em 26/11/2026, o serviço Railway leadcob-pncp está sem cron, sem réplica em execução e usa um deploy de 12/11. Não comprova atualização diária. A correção em branch independente trata três defeitos reproduzíveis: JSON malformado contado como vazio válido, volume lido arredondado para páginas de 50 e limite de páginas reportado como captura completa.

O coletor agora rejeita páginas inválidas, aceita ausência HTTP 204/404 como consulta vazia válida, usa a data da execução informada e conta linhas realmente lidas. Paginação incompleta/limitada emite coverage_limited e resulta em status partial na API. Confirmação oficial precisa corresponder ao número de controle e conter objeto. O job termina com código 2 em captura parcial, 1 em falha, 0 somente quando completa dentro das modalidades consultadas. Isso não equivale à cobertura de todas as modalidades do PNCP ou de outras fontes do Radar.

Diagnóstico sem gravação: `python -m app.jobs.capture_pncp --probe --days 1 --max-pages 1`. Sem --probe, mantém execução produtiva existente e exige schema correto. Não executar o modo produtivo sem autorização para captura.

Proposta operacional, ainda não ativada: reutilizar leadcob-pncp, fixar SHA aprovado com CI verde, usar `python -m app.jobs.capture_pncp --days 2 --max-pages 5`, cron `15 12 * * *` (08h15 Manaus), restart NEVER, uma réplica e conexão privada existente. Até 30 páginas iniciais (6 modalidades × 5), até quatro tentativas por requisição. Falhas e cobertura parcial precisam revisão; não ampliar páginas para esconder status parcial. Homologar primeira execução e a próxima ocorrência agendada, com CaptureRun, horários, volume e amostra de fontes.

Nenhum cron, gasto novo ou escrita produtiva foi ativado. Testes locais: compileall e 421 testes aprovados, incluindo 21 regressões de captura/job. O ensaio remoto --probe é diagnóstico, não homologação do job produtivo.
