# Auditoria de lançamento — 17/11/2026

Evidência do #134: backend 243 testes aprovados, 8 avisos; PostgreSQL 3 testes aprovados; workflow browser e implantação online aprovados. Execuções: https://github.com/L3GEND7x/leadcob-ai/actions/runs/44172457855, https://github.com/L3GEND7x/leadcob-ai/actions/runs/44172457505, https://github.com/L3GEND7x/leadcob-ai/actions/runs/44172457467. Evidência não equivale a auditoria completa ou homologação de produção.

#135 adiciona painel administrativo de prontidão que consulta a API existente, sem mutações nem exposição de chaves. Estado real de configuração do servidor não foi consultado nesta auditoria. Testes visuais deste painel e CI pendentes.

## Decisão: não liberar lançamento amplo
- P0: homologar Pix/boleto, webhook, estornos e recuperação de emissão incerta no Asaas sandbox real; nenhuma chamada externa realizada.
- P0: pagamentos de produção e assinatura recorrente não implementados; não anunciar como disponíveis. Baixa manual exige conferência bancária independente.
- P0: validar backup/restauração, revisão de migração e recuperação de incidentes.
- P0: revisão de privacidade, termos, retenção e atendimento.
- P1: E2E administrativo financeiro completo, segurança das rotas legadas, concorrência adicional PostgreSQL (emissão versus vínculo/cancelamento).
- P1: revisar avisos do CI, testar acessibilidade e navegadores adicionais.
- P1: validar captação, contatos e assistente IA com dados e credenciais reais autorizados; este ciclo comercial não demonstra funcionamento integral desses módulos.

Não ativar flags, chaves ou cobranças nesta entrega. Piloto somente após aceite dos gates aplicáveis, registro de evidências e aprovação do responsável. Planos preservados: Essential R$27, Professional R$117, Enterprise R$397/mês.
