# Retomada verificada — 26/11/2026

## Release e coletor

#220 foi o ponto de partida. #222 (f9f4923) passou cinco workflows, incluindo ensaio externo real: 5 sites, 5 e-mails funcionais reencontrados com origem; execução 45873508024. Proprietário autorizou merge/implantação neste atendimento. Merge 68d812124bb5fec26687361ee23d99865d8a089d passou os três workflows de main. Railway deployment 801bb727-4343-46a3-83a3-c8d861298c1f observado SUCCESS. Somente leadcob-web atualizado, mantendo SHA fixo. Sem ativar Assistente IA, serviços, importações ou cobranças.

## Evidências de dados e operação

Preflight privado do deploy #218 às 11h58 Manaus: 14.225 CNPJs válidos únicos em Manaus, zero duplicados locais, 14.212 identidades corporativas elegíveis e zero canais diretos. São contagens daquele snapshot, não censo municipal nem estado após piloto. Coleta externa no Actions não gravou esses contatos no banco.

Backup de 26/11 às 00h04 Manaus: snapshot e741b234 conferido; restauração isolada de 49 tabelas concluída. Não certifica conteúdo de negócio nem retenção definitiva.

Radar: serviço leadcob-pncp sem cron, sem réplica em execução e com deploy de 12/11. Probe real somente leitura: seis páginas, 252 registros de 8.033 disponíveis, cinco limitações; cobertura parcial corretamente sinalizada na branch #223. Jobs, Querido Diário e DataJud não foram homologados neste atendimento. Não há worker de contatos dedicado no inventário Railway; ativação depende de piloto, medição e autorização de custo.

## Dimensionamento antes das cargas

Métricas Railway (24h, amostras horárias): PostgreSQL usa cerca de 0,150 GB de disco em volume configurado de 500 MB; memória média 0,061 GB. Web: memória média 0,126 GB, pico amostrado 0,446 GB. Não extrapolar esses dados para carga nacional: faltam contagem oficial elegível por competência, bytes por linha com índices, WAL, staging e throughput medido.

Preços de referência consultados em https://docs.railway.com/pricing em 26/11/2026: RAM US$10/GB-mês, CPU US$20/vCPU-mês, volume US$0,15/GB-mês, saída de rede US$0,05/GB. Estimativas abaixo são cenários de consumo, não cotação, limite de cobrança nem previsão de capacidade:

| Cenário hipotético | Hipótese | Consumo estimado |
|---|---|---|
| Worker contínuo pequeno | 0,10 GB RAM + 0,01 vCPU por 30 dias | US$1,20/mês, mais rede |
| PNCP diário | 30 execuções de 10 min, 0,25 GB RAM + 0,25 vCPU | US$0,052/mês, mais rede |
| Staging temporário | 20 GB por 24h + 1 GB RAM e 1 vCPU por 4h | US$0,267 por execução, mais rede |
| Base ampliada, hipótese | 5 GB disco + 0,5 GB RAM + 0,05 vCPU por mês | US$6,75/mês, mais rede |

Fórmula: (10×GB_RAM+20×vCPU)×horas/720 + 0,15×GB_disco×dias/30 + 0,05×GB_saida. Valores não incluem mínimo do plano, créditos, tributos, câmbio, Backblaze, outros serviços ou margem. Não há aprovação de gastos.

AM requer 10 partições; Norte, 70 células; Brasil, 270 células lógicas da mesma competência. Manifesto, preflight e staging existentes devem ser reutilizados. Próximo passo autorizado sem carga: validar metadados da competência e benchmark isolado; só depois solicitar teto concreto de recursos. O volume atual de 500 MB não deve receber carga nacional sem dimensionamento. Não foram baixados ZIPs maciços nem executado --apply.

## Segurança e liberação comercial

Assistente IA permanece removido da interface. Login exigido no navegador; sem sessão do proprietário neste ambiente. Smoke anônimo não valida isolamento autenticado. Testes existentes cobrem sessão, CSRF, isolamento, planos, cobrança sandbox, backup e supressão; produção comercial permanece desativada. Catálogo esperado preservado: Essential R$27, Professional R$117, Enterprise R$397. Nenhuma cobrança ou assinatura real habilitada. API de branch protection retornou 403 por permissão da integração; proteção do repositório não foi certificada.

Pendências reais: homologação autenticada, piloto produtivo por CNPJ (JSON atual com ownership_reviewed=false), revisão humana dos canais, demonstração da execução diária, fila/worker em produção, cobertura territorial, retenção operacional, revisão jurídica de privacidade/termos, sandbox de pagamento e liberação comercial. Rotas legadas individuais de enriquecimento ainda exigem revisão de elegibilidade; não afirmar auditoria integral concluída.

## Próxima decisão

#223 e #224 são PRs independentes; CI verde e autorização ainda exigidos antes dos merges. Para o piloto: entrar como proprietário, prévia de no máximo cinco registros, conferir existência/elegibilidade/ausência de supressão e aprovar os elegíveis. Processar um por vez, conciliar contatos antes/depois e preservar status a verificar. Não criar empresas ausentes nem enviar mensagens. A autorização de #222 não inclui essa gravação.
