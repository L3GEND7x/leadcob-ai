# PR #168 — Worker de contatos habilitável com segurança

## Comportamento
- `CONTACT_DISCOVERY_WORKER_ENABLED=false` por padrão. O worker **não chama sites nem retira itens da fila** quando esta variável está desativada.
- `python -m app.jobs.discover_contacts --probe`: consulta somente métricas agregadas da fila; nenhuma coleta, criação de contato ou envio de mensagem. A revisão Alembic é checada em produção.
- `CONTACT_DISCOVERY_WORKER_ENABLED=true python -m app.jobs.discover_contacts --max-items 3`: até três tentativas por execução sobre lotes **incluídos manualmente pelo proprietário**. Não procura automaticamente todos os CNPJs e não envia mensagens por WhatsApp, e-mail ou outros canais.
- Retenção dos registros históricos de heartbeat: 30 dias, sem excluir lotes ou resultados.
- O processamento compartilha a proteção existente de CNPJ, supressão, site institucional já cadastrado, robots.txt, URLs públicas, fontes rastreáveis e contatos não verificados. Consumo real de rede só ocorre após habilitar expressamente o worker.

## Implantação opcional de baixo volume
Serviço Railway privado dedicado; imagem `infra/Dockerfile`, start `python -m app.jobs.discover_contacts --max-items 3`, variável `DATABASE_URL` referenciada à conexão privada Postgres, nenhuma porta/dominio público. Primeiro rodar `--probe`, depois autorizar coleta de lotes de teste no painel e ativar flag. Se agendado por cron, iniciar com uma execução a cada 30–60 minutos, **não** rodar com --continuous no primeiro teste. Cron pode gerar custo; verificar preço e limites do plano Railway.

## Limites de homologação
- Probe apenas verifica conexão, esquema e fila; não comprova captação ou contatos.
- Para coleta real, verificar manualmente a titularidade do site e a autorização institucional, testar 1–3 empresas e inspecionar erros sem divulgar dados pessoais.
- A implementação não cria um serviço automaticamente; é necessária implantação e monitoramento.
- Desativar a flag interrompe novas execuções mas não necessariamente uma iteração já iniciada.
