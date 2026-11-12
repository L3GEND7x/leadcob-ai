# Manual de uso diário — LeadCob AI 0.5.3

Rotina sugerida de 30 a 60 minutos por dia. Tudo o que aparece nas telas vem do banco do sistema
(fontes públicas captadas e o que você registra). Nada é enviado a empresas pelo sistema: contato,
cobrança, protesto, negativação ou notificação dependem sempre de decisão e ação humanas.

## 1. Central de comando (manhã, 5 min)
- **Follow-ups atrasados**: tarefas e "próximas atividades" vencidas. Resolva ou reagende primeiro.
- **Precisam de abordagem**: empresas em "Qualificada" ou "Pronta para abordagem" sem contato.
- **Novos sinais (7 dias)** e **Sinais recentes**: editais e vagas captados, com link para a fonte.
- **Funil**: quantas empresas há em cada uma das 13 etapas.
- Indicadores: contatos, respostas, reuniões, propostas, contratos e conversão (contratos ÷ empresas
  contatadas). **Valor potencial** é a soma do que você informou nas fichas; o sistema não estima valores.

## 2. Inteligência do dia (10 min)
Cinco empresas escolhidas por regras explicáveis (sem modelo de linguagem). Cada cartão traz:
- **Por que hoje**: os três componentes da pontuação que mais pesaram;
- **Evidência**: o sinal mais forte, com fonte e data (fato) — ou o aviso de que não há sinal (hipótese);
- **Serviço sugerido**, **Como iniciar** (texto para adaptar), **Canal** e **Próxima ação**;
- **Fatos / Indícios / Hipóteses** separados;
- o lembrete: não afirme que a empresa tem inadimplência — nenhuma fonte usada aqui comprova isso.

Ficam de fora: empresas encerradas no funil, na lista de supressão, concorrentes (CNAE 8291),
com cadastro inativo e as contatadas há menos do intervalo configurado (padrão: 7 dias).

## 3. Ficha da empresa (durante as abordagens)
- **Etapa e próxima atividade**: mude a etapa, defina a próxima atividade e a data, informe o valor
  potencial (se souber) e anotações. "Perdido" exige motivo.
- **Registrar interação**: contato, follow-up, resposta, reunião, proposta, contrato ou anotação, com
  canal e data. Contato, resposta, reunião, proposta e contrato **avançam a etapa** automaticamente
  (nunca a fazem voltar). Marque "follow-up em N dias" para criar a tarefa.
- **Trava contra abordagem repetida**: um novo contato antes do intervalo mínimo pede confirmação.
- **Não contatar (opt-out)**: inclui a empresa na lista de supressão. Daí em diante ela não recebe
  contato, não muda de etapa, não aparece na busca (salvo pedido) nem na exportação.
- **Por que esta pontuação**: cada componente com pontos, motivo e natureza (fato, indício, hipótese).
- **Sinais e evidências**: origem de cada informação e a ressalva de leitura (edital público ≠ oportunidade
  privada; vaga de cobrança ≠ interesse em terceirizar).
- **Contexto regional (DataJud)**: volume de cobrança judicial na UF — não diz nada sobre a empresa.

## 4. Encontrar empresas (prospecção, quando o funil esvaziar)
Filtros: nome/CNPJ, região, UF(s), município, perfil do setor, tipo de inadimplência típico, CNAE
(principal e secundários), porte, situação cadastral, capital social, anos de atividade, etapa, faixa
de pontuação e "com/sem sinal". Ordene por pontuação, capital, nome, antiguidade ou sinal recente.
"Adicionar empresa" cadastra uma PJ à mão (o CNPJ evita duplicidade). "Exportar CSV" (versão
instalada) traz só dados de PJ e exclui a lista de supressão.

## 5. Sinais e oportunidades
Busque editais (PNCP) e vagas (Greenhouse/Lever), cadastre um sinal com a evidência observada e rode
os agentes (pesquisa → qualificação → auditoria → supervisor) para ver o que falta confirmar.

## 6. Radar de mercado e Fontes
O radar mostra, por UF, volume e tipo de cobrança ajuizada (DataJud). "Fontes de dados" mostra cada
fonte como Integrada e testada, Com erro de coleta, Consultada, Indisponível ou Planejada.

## 7. Configurações
UFs de atuação (pesam na pontuação), intervalo mínimo entre contatos, serviço oferecido, lista de
supressão (incluir por CNPJ, retirar) e exportação.

## Página publicada (claude.ai)
- Atualiza sozinha de hora em hora (aos 10 minutos, horário de Manaus).
- Ações do CRM feitas na página ficam salvas no banco da página e valem na hora na tela. A pontuação, a
  central de comando e a inteligência do dia incorporam essas ações na atualização seguinte (o aviso no
  topo mostra quantas aguardam o recálculo).
- Limitações da página: sem consulta de CNPJ e sem exportação CSV (a página não acessa sites externos);
  os sinais refletem a janela de captação atual (PNCP dos últimos 7 dias e vagas abertas). Para histórico
  completo e volumes maiores, use a versão instalada com servidor próprio.

## 8. Abordagem sugerida (na ficha)
"Gerar e-mail, WhatsApp, roteiro e follow-ups" monta os textos com os fatos da ficha (vaga ou setor) e sua assinatura
(Configurações). Copie, ajuste e envie você mesma; depois clique em "Registrar como enviado" e confirme o registro.
Para órgãos públicos com edital, o sistema mostra só o checklist: a comunicação segue o edital.

## 9. Inteligência de cobrança (clientes que contrataram você)
Importe a carteira do cliente em CSV (colunas `valor` e `vencimento`; opcionais `pagamento`, `titulo`, `tipo_devedor`).
Nome, CPF e contatos de devedores são descartados. Veja as faixas de atraso e a estratégia sugerida para cada uma;
mude a data de referência para simular outro dia. Na página publicada este módulo não recebe carteiras (dados de terceiros).

## 10. Laboratório de negociação
Informe valor, vencimento, data-base e as premissas (correção, multa, juros, desconto, entrada, parcelas). Campos em branco
valem zero. Confira limites contratuais e legais antes de propor. A memória de cálculo mostra cada passo.

## 11. Biblioteca de scripts
Modelos de abertura, descoberta, objeções, follow-up e cobrança da carteira, com busca e botão de copiar.

## 12. Contatos empresariais
Lista de canais institucionais com origem e status, com filtros por UF e município. "Sincronizar fichas" importa só site e
e-mail já cadastrados. Na ficha, a leitura do **site oficial cadastrado** (versão instalada) registra e-mails de setor, telefone,
WhatsApp e páginas da empresa no LinkedIn, Instagram e Facebook que o próprio site publica, sempre com a página de origem e o
status **a verificar**. Confira cada canal antes de usar e marque como verificado ou inválido. Um número publicado pode ser de
uma pessoa: trate como dado pessoal e use só para o contato comercial com a empresa.

## 13. Relatórios
Resumo dos últimos 7 ou 30 dias: contatos, respostas, reuniões, propostas e contratos registrados; conversão das
empresas contatadas; movimento no funil; motivos de perda; sinais novos por fonte; tarefas. Na versão instalada,
"CSV" baixa o mesmo relatório. São contagens do que você registrou: sem estimativas.

## 14. Agenda
Tarefas abertas, atrasadas e concluídas, com a empresa de cada uma. Reagende pela data e hora ou marque como concluída.

## 15. Assistente LeadCob
Consulta dados do sistema e prepara abordagens. **Só funciona** com chave da API da OpenAI, modelo, preços por token e orçamento
mensal configurados no servidor; sem isso, a tela avisa e nenhuma chamada paga é feita. Ações sugeridas pelo assistente (ex.:
criar tarefa) só valem depois da sua confirmação. Se a chamada falhar antes de chegar à OpenAI, a reserva do orçamento volta.
