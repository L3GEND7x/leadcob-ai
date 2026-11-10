# Como trabalhamos neste repositório (Claude + ChatGPT + proprietária)

O LeadCob AI é desenvolvido por dois assistentes de IA — **Claude** (Claude Code) e **ChatGPT** — sob decisão
da proprietária do projeto. Os assistentes não conversam entre si diretamente: **o repositório é o ponto de
encontro**. Este arquivo é o combinado que os dois seguem. Leia antes de abrir qualquer PR.

## 1. Fluxo de trabalho
- Nunca enviar commit direto para `main`. Cada mudança vai em um ramo próprio e um **PR**.
- Prefixo do ramo identifica o autor: `claude/...` ou `chatgpt/...` (ramos antigos `feat/`/`fix/` continuam válidos).
- **Um PR = um assunto.** PR pequeno é revisado mais rápido e quebra menos coisa.
- Antes de começar algo grande, abrir uma **issue** com o plano; quem pegar a issue se atribui nela,
  para os dois não fazerem a mesma coisa ao mesmo tempo.
- Todo PR de um assistente pode ser **revisado pelo outro**; o merge é sempre decisão da proprietária.

## 2. O que todo PR precisa ter
- Testes passando: `cd backend && python -m pytest -q` (o CI roda o mesmo).
- Teste novo para regra nova (ex.: supressão, deduplicação, cálculo).
- Descrição com: o que muda, por que, como foi testado e o que ficou pendente.
- CHANGELOG atualizado quando muda comportamento visível.
- Se mudar algo que a página publicada ou a tarefa horária usa (`scripts/build_dashboard_snapshot.py`,
  `scripts/snapshot_runtime.js`, variáveis de ambiente, workflows), **dizer isso no PR** — a página atualiza
  sozinha de hora em hora a partir da `main`.

## 3. Regras do projeto (não negociáveis)
- **Não inventar** fatos, empresas, contatos, leis, números ou jurisprudência. Sem informação: `[INFORMAÇÃO NÃO LOCALIZADA]`
  ou `[NECESSÁRIO CONFERIR]`.
- Separar **fato / indício / hipótese** em tudo que aparece para a usuária.
- **Só dados de pessoa jurídica** na prospecção. Sem CPF, sócios, e-mail ou telefone pessoais. Dados de devedores
  ficam só na inteligência de cobrança da versão instalada, com o mínimo necessário.
- **Nenhum envio automático** de mensagem, cobrança, protesto ou negativação: tudo depende de ação humana.
- Lista de supressão ("Não contatar") sempre respeitada.
- Sem dados fictícios apresentados como reais (exemplos só com `DEMO_SEED=true`).
- Fonte só vira "Integrada e testada" depois de testada com dados reais.
- **Segredos nunca no código**: chaves privadas, senhas e tokens vão em variáveis de ambiente / segredos do GitHub.
  Valores públicos necessários (ex.: chave pública do DataJud, token do compartilhamento da Receita) também ficam
  fora do código, em variável documentada.

## 4. Quem cuida do quê (atual)
| Área | Responsável principal | Observação |
|---|---|---|
| Página publicada (claude.ai) e tarefa horária | Claude | `scripts/build_dashboard_snapshot.py`, `scripts/snapshot_runtime.js` |
| Importação da Receita no Actions (`importar-cnpj.yml`, ramo `dados-cnpj`) | Claude | |
| Instalação em servidor próprio, login, backup (`docker-compose.cloud.yml`, `core/security.py`) | ChatGPT | PR #14 |
| Assistente com IA (`routes_assistant.py`) | ChatGPT | exige chave de API e orçamento |
| CRM, pontuação, abordagens, cobrança, negociação | compartilhado | revisar o PR do outro |

Mudou a divisão? Atualize esta tabela no próprio PR.

## 5. Revisão entre assistentes
Ao revisar o PR do outro, comentar no PR com:
1. **Bloqueante** — quebra teste, regra do projeto, página publicada ou segurança;
2. **Sugestão** — melhoria que não impede o merge;
3. **Pergunta** — dúvida de intenção.
Não reescrever o PR do outro sem combinar: propor a mudança no comentário ou abrir um PR em cima.

## 6. Situação atual e próximos passos
Ver `docs/status-v0.5.md`, `docs/roadmap.md` e as issues abertas.
