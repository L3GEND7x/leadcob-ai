# Situação da entrega 0.5.0 (09/11/2026) — Etapa 1 do plano de evolução

Plano em três etapas, conforme a recomendação recebida:
1. **Etapa 1 (esta entrega):** central de comando, inteligência do dia, prospecção nacional, qualificação e CRM.
2. Etapa 2: gerador de abordagens, inteligência de cobrança (faixas de atraso), estratégias de recuperação,
   laboratório de negociação, biblioteca de scripts e biblioteca de conhecimento com fontes verificadas.
3. Etapa 3: agentes especializados, pesquisa contínua, relatórios e automações.

## Integrado e testado nesta entrega

| Módulo | O que funciona | Onde |
|---|---|---|
| Central de comando | Indicadores (empresas, novas hoje, sinais novos, qualificados, não abordados, contatos, respostas, reuniões, propostas, contratos, conversão, valor potencial informado), funil de 13 etapas, listas de trabalho | `GET /api/command-center` · tela "Central de comando" |
| Inteligência do dia | 5 empresas com motivo, evidência (fonte e data), serviço sugerido, como iniciar, canal, próxima ação, fatos/indícios/hipóteses separados | `GET /api/daily-intelligence` |
| Prospecção nacional | Busca em todo o Brasil por nome/CNPJ, região, UF, município, CNAE (principal e secundários), perfil, tipo de inadimplência, porte, situação, capital, anos de atividade, etapa, faixa e sinal; ordenação e paginação; cadastro manual com deduplicação por CNPJ (e por nome, sem CNPJ) | `GET /api/companies/search` · `POST /api/companies` |
| Lead score explicável | 0–100 com 8 componentes, cada um com motivo e natureza; faixas 80/60/40 | `docs/lead-score.md` |
| CRM | 13 etapas, ficha completa, histórico, interações, tarefas, próxima atividade, valor potencial, motivo de perda, lista de supressão, trava contra abordagem repetida, auditoria de toda mudança | `PATCH /api/companies/{id}`, `/interactions`, `/tasks`, `/suppression`, `/settings`, `/pipeline` |
| Fontes | Cinco estados: Integrada e testada, Com erro de coleta, Consultada, Indisponível, Planejada | `GET /api/sources` |
| Exportação | CSV só com dados de PJ e sem empresas suprimidas (auditada) | `GET /api/export/companies.csv` |
| Interface | 8 módulos navegáveis, computador e celular (testados sem erros e sem rolagem lateral) | `frontend/` |
| Página publicada | Mesmas telas; ações do CRM gravadas no banco da página e reaplicadas a cada atualização horária, com a hora original | `scripts/build_dashboard_snapshot.py`, `scripts/snapshot_runtime.js` |
| Migração | Bancos antigos recebem as colunas e tabelas novas no startup | `ensure_schema()` |

Também nesta entrega: os 3 registros fictícios de demonstração das versões anteriores deixaram de ser
criados (só com `DEMO_SEED=true`) e são removidos dos bancos existentes.

## Relatório de testes
- `python -m pytest` (backend): **118 testes aprovados**, sendo 15 novos (CRM, pontuação, central de
  comando, inteligência do dia, supressão, exportação, migração, remoção de dados fictícios e reaplicação
  das ações da página publicada).
- Teste de interface (Playwright, Chromium) nas 10 telas, em 1366×900 e iPhone 13: sem erros de
  JavaScript e sem rolagem horizontal. Fluxos executados no navegador: registrar contato, aviso de contato
  repetido e confirmação, "Perdido" sem e com motivo, tarefa, supressão e bloqueio, configurações, busca
  por nome e por região, cadastro duplicado recusado.
- Página publicada testada com banco simulado: ações gravadas, aplicadas na tela e reaplicadas pelo
  script na rodada seguinte.

## Pendente (não marcado como pronto)
- Etapa 2 e Etapa 3 inteiras (lista acima). Aparecem no menu como "Em construção".
- Biblioteca de conhecimento jurídico: as referências recebidas (Código Civil — inadimplemento e mora;
  CPC arts. 783 e 784; Lei 9.492/1997; CDC art. 42; materiais do CNJ, PGFN, Sebrae e ANPD) só entram
  depois de conferidas na fonte oficial. **[NECESSÁRIO CONFERIR]** — o planalto.gov.br não respondeu
  deste ambiente.
- Termo de uso da API pública do DataJud: **[NECESSÁRIO CONFERIR]** (página carregada por JavaScript).
- Autenticação, HTTPS e hospedagem própria: necessários antes de uso por equipe ou exposição na internet.
- Sinais de terceirização: nenhuma fonte pública comprova essa demanda; continuam como hipótese.
- Calibração dos pesos da pontuação com resultados reais do CRM.

## Atualização 0.5.2 (10/11/2026) — início da Etapa 2
Integrado e testado: aba Contatos (pacote 0.5.1 revisado), identidade violeta, gerador de abordagens, inteligência de
cobrança por faixas de atraso com estratégia sugerida, laboratório de negociação e biblioteca de scripts.
Testes: **127 aprovados** (121 do pacote 0.5.1 + 6 novos da Etapa 2). Interface testada no Chromium em 1366×900 e
iPhone 13 (9 telas, sem erros de JavaScript e sem rolagem horizontal).
Pendente: agentes especializados, pesquisa contínua, relatórios; base de conhecimento jurídico só com fontes conferidas
([NECESSÁRIO CONFERIR]); pesquisa institucional de contatos por CNPJ em sites oficiais (com fonte e revisão humana);
carteiras de cobrança na página publicada (fora por segurança: dados de devedores de terceiros).
