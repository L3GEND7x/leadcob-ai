# Revisão de produção — 11/11/2026

Revisão feita pelo Claude a partir do código da `main` (`77a8b1b`) e de testes locais. **Não houve acesso à
Railway nem à Backblaze**: o que depende do ambiente real está em "Não testado". Nenhum valor de variável foi lido.

## 1. Falhas comprovadas

| # | Falha | Como foi comprovada | Situação |
|---|---|---|---|
| F1 | O Restic falha com `invalid header field value for "Authorization"` quando `AWS_ACCESS_KEY_ID` (ou `AWS_DEFAULT_REGION`) tem quebra de linha | Reproduzida em teste local com valores falsos. Espaço, tab, aspas e rótulo **não** causam esse erro | O script passa a parar antes, com mensagem clara (PR #32). **A correção do valor na Railway depende da proprietária** |
| F2 | Trocar `ADMIN_PASSWORD_HASH` não encerrava as sessões abertas: elas continuavam válidas por até 8 h, também depois de reiniciar | Teste automático falhava antes da correção | Corrigido no PR #34 |
| F3 | O bloqueio de login usa um contador único (`key = 'owner'`). Cinco tentativas erradas de **qualquer pessoa** bloqueiam o login da proprietária por 15 min | Leitura do código (`core/security.py`) | **Não corrigido.** Protege contra adivinhação, mas permite bloquear o acesso de propósito. Sugestão para o ChatGPT: limitar também por IP antes do contador da conta |

## 2. Assistente (API da OpenAI) — conferido no código

- **Desligado por padrão.** Só funciona com `OPENAI_API_KEY`, `OPENAI_MODEL`, `ASSISTANT_MONTHLY_BUDGET_USD`,
  `OPENAI_INPUT_USD_PER_MILLION` e `OPENAI_OUTPUT_USD_PER_MILLION` todos preenchidos e maiores que zero. Sem isso a API responde 503 e
  nenhuma chamada paga acontece. Hoje: [NECESSÁRIO CONFERIR NA RAILWAY] se alguma dessas variáveis existe.
- **Chave:** lida só da variável de ambiente; não aparece em respostas nem logs (falhas registram só o tipo do erro).
- **Orçamento:** antes de cada pergunta o sistema reserva o pior caso: `0,384 × preço de entrada + 0,008 × preço de saída` (em
  US$, com preços em US$ por milhão de tokens). Exemplo de leitura: com orçamento mensal B, cabem pelo menos
  B ÷ (esse valor) perguntas no mês. Depois da resposta a reserva é trocada pelo custo real.
- **Risco:** se a chamada falhar, a reserva **não é devolvida** (escolha conservadora do código). Várias falhas seguidas podem
  esgotar o orçamento do mês sem nenhum gasto real. Sugestão: devolver a reserva quando a falha comprovadamente ocorreu antes do envio.
- **Preços e modelo:** precisam ser copiados da página oficial de preços da OpenAI para o modelo escolhido, na data da
  configuração. [NECESSÁRIO CONFERIR] — não foram informados aqui de propósito. Se os preços estiverem abaixo do real, o
  limite do sistema deixa de proteger.
- **Proteção adicional recomendada:** definir também um limite de gastos no projeto da conta OpenAI (opções e nomes no painel da
  OpenAI: [NECESSÁRIO CONFERIR]), porque o limite do LeadCob só controla as chamadas feitas pelo LeadCob.
- Outros pontos do código: `timeout=45`, `max_retries=0`, `store=False`, no máximo 4 rodadas e 8 ferramentas por pergunta,
  ações do assistente exigem confirmação humana.

## 3. Não testado (riscos a conferir no ambiente real)

| Ponto | Por que não foi testado | O que conferir |
|---|---|---|
| Backup real para o bucket `leadcob-ai-backup` | Sem acesso à Railway/B2 | Log com as 4 etapas, `restic check` sem erros e snapshot listado |
| Restauração com PostgreSQL 18 | Ensaio local usou PostgreSQL 16 | Ensaio na Railway (PR #33) |
| Alertas de falha do cron | Sem acesso; opções de notificação da Railway: [NECESSÁRIO CONFERIR] | Que uma execução com falha gere aviso por e-mail ou outro canal |
| Deploy, healthcheck e migração (`alembic upgrade head` no pre-deploy) | Sem acesso | Log do pre-deploy e `/api/health` |
| Privacidade do bucket e escopo da chave B2 | Sem acesso | Bucket privado; chave restrita a esse bucket; chave antiga (exposta) revogada |
| Logs do servidor | Sem acesso | O uvicorn registra o caminho das requisições, incluindo termos de busca na URL. Sem senhas ou chaves no código revisado |
| Página do claude.ai | — | Está compartilhada com "qualquer pessoa com o link". Contém só dados públicos de PJ; decidir se mantém |

## 4. Isolamento dos dados

- Um único proprietário por instalação; todas as rotas exigem sessão em produção, gravações exigem token CSRF e mesma origem
  (testes existentes).
- A prospecção usa só dados de PJ. A inteligência de cobrança descarta nome, CPF e contato de devedores na importação.
- **Não importar carteiras ou dados financeiros reais** antes de: backup real com snapshot + ensaio de restauração real.

## 5. Atualização — 12/11/2026

| Item | Situação |
|---|---|
| F1 (Restic e quebra de linha) | **Resolvido.** A credencial foi corrigida na Railway. Backup real `a788ae04` e ensaio de restauração real OK (`docs/ensaio-restauracao.md`). |
| F2 (sessões após troca de senha) | **Corrigido** no PR #34, revisado pelo ChatGPT. |
| F3 (bloqueio de login global) | **Aberto.** O ChatGPT confirmou o risco. A correção depende de validar qual IP real a Railway repassa ao app. |
| Reserva do assistente não devolvida | **Corrigido** no PR #38: a reserva volta quando a falha ocorre antes da chamada à OpenAI. |
| Starlette 0.46.2 com avisos de segurança | Atualização para FastAPI 0.162.5 / Starlette 1.10.0 proposta em PR. `pip-audit` sem vulnerabilidades. |
| Sem CSP/HSTS | Cabeçalhos propostos em PR, testados nas 15 telas sem violação. |
| Banco de produção com dados reais | O importador do PR #41 pode ter carregado ~23 mil empresas. **Repetir o ensaio de restauração** com esses dados ([NECESSÁRIO CONFERIR] se a importação já rodou). |

**Auditoria de 12/11 no app rodando** (PostgreSQL, Alembic, login e 3.000 empresas reais da base AM; navegador com Playwright):
- 15 telas sem erro de JavaScript;
- 28 verificações de fluxo OK;
- teste de XSS em 7 campos sem execução;
- telas no tamanho de celular (390 px) sem transbordar;
- `alembic check` sem diferença entre modelos e migrações;
- `ruff` sem erros reais: os avisos restantes são o padrão `Depends` do FastAPI ou falsos positivos.
