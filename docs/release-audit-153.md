# LeadCob AI — auditoria de liberação comercial #153

**Decisão: NO-GO para comercialização irrestrita.** Ciclo de desenvolvimento não equivale a homologação produtiva.

## Evidências verificadas
- #152 mesclado na main. Backend aprovado; integração financeira e benchmark aprovados no job PostgreSQL; browser e implantação online aprovados. Workflow Testes 44222823501 falhou em pg_restore (job 134528636098): PostgreSQL 18.6 client versus servidor 16.16, rejeição de SET transaction_timeout. #153 usa ferramentas da imagem PostgreSQL 16, exige mesma versão principal e exibe erro limitado no ensaio sintético. Novo CI ainda pendente.
- #150 benchmark sintético PostgreSQL 53.000 CNPJs, 13.250 contatos, mediana 0,853s inventário/1,843s qualificação/1,082s lacunas; quatro consultas simultâneas concluídas em 3,361s/7,114s/4,010s respectivamente; pico processo 347568 KiB. Fonte run 44221872741. Não mede produção.
- #143 testes de jornada e isolamento de duas organizações aprovados em CI; #148 contexto privado determinístico; #149 consulta pública individual e inclusão manual no CRM; #151 testes de segregação sandbox e razão financeiro aprovados. Não certificam todo o sistema.

## Bloqueios P0 e evidência exigida
| Área | Pendência | Aceite |
|---|---|---|
| Recuperação | Ensaio #152 falhou; backup produtivo não configurado ou verificado nesta auditoria | CI de restauração aprovado, restauração isolada de cópia autorizada com migrações, retenção, RPO/RTO e teste de integridade |
| IA do proprietário | Chave, modelo, saldo e respostas reais não testados | Consulta explícita de metadados, geração curta com orçamento autorizado, ferramentas e aprovação de tarefas em ambiente descartável |
| IA comercial | Sem chat, histórico privado ou orçamento por organização | Migrações, autorização por usuário e tenant, idempotência, retenção/exclusão, limites globais e individuais, CI e teste real |
| Cadastro | Universo de Manaus desconhecido; importador de filiais e atualização de baixas exige revisão | Competência, filtros e denominador comparável; conferir amostra, corrigir associação por raiz e reconciliação de baixas |
| Contatos | Coletor e fila testados com fixtures, sem captação real verificada | Sites oficiais revisados, amostra autorizada, origem e cobertura, tratamento de sem site e de supressões |
| Worker | Diagnóstico local não comprova atividade; lease vencido pode duplicar coleta | Heartbeat, teste de concorrência PostgreSQL e atomicidade da gravação/finalização |
| Prospecção comercial | Consulta individual por CNPJ; sem pesquisa por cidade; sem rate limit dedicado, deduplicação estruturada ou revalidação de supressão na inclusão | Rate limit e quotas antes de exposição ampla, inclusão consistente por CNPJ e base pública segregada |
| Financeiro | Asaas sandbox não homologado externamente, integração produtiva ausente | Testar PIX/boleto sandbox autorizado, webhook/replay, divergência, estorno, conciliação; revisão separada da integração real |
| Segurança e privacidade | Sem pentest completo, revisão LGPD e termos pendentes | Revisão de autorização por rota, segredos, logs, retenção, exclusão, incidentes, termos e base legal por responsável |
| Desempenho | Benchmark restrito a serviços e dados sintéticos | Testar HTTP e carga mista em staging, limites de recursos e concorrência, medir gargalos e estabelecer SLO |

Catálogo preservado: Essential R$27, Professional R$117, Enterprise R$397 por mês. Nenhum preço, cobrança ou assinatura real alterados.

## Próximas ações propostas
Primeiro corrigir e verificar CI de restore; depois etapa de homologação operacional autorizada em staging, com evidências dos bloqueios acima e responsáveis. Não marcar release_ready como true automaticamente. #153 atualiza o painel de prontidão para explicitar os gates. Não acessa banco produtivo, não faz chamadas reais a provedores nem executa pentest. Auditoria delimitada ao código e evidências CI inspecionados, não certificação legal ou de segurança.
