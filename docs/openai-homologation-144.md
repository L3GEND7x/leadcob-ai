# Homologação OpenAI

#143 mesclado e três workflows aprovados. #144 adiciona verificação explícita de metadados do modelo pela Assistente proprietária. Requer configuração local completa. POST protegido por sessão/CSRF existentes; timeout 10s, sem retries, sem geração nem dados do cliente. Registra auditoria sanitizada. Resultado não comprova saldo, autorização de Responses, capacidade de ferramentas ou geração.

## Aceite pelo proprietário
1. Configurar OPENAI_API_KEY e OPENAI_MODEL no servidor, com orçamento e preços reais por milhão de tokens. Não enviar chave no chat, repositório ou logs.
2. Na Assistente IA, clicar Verificar acesso ao modelo. Registrar horário e resultado.
3. Se acessível e houver orçamento autorizado, enviar uma mensagem curta sem dados reais de clientes (ex.: Responda apenas OK). Conferir resposta, histórico e consumo estimado.
4. Em seguida, testar uma consulta de dados autorizada e uma proposta de tarefa em ambiente descartável. Confirmar que proposta não cria tarefa sem aceite. Conferir cobrança real no provedor e erros.
5. Não liberar IA a assinantes até isolamento por organização.

Nenhuma chamada externa realizada nesta revisão; credenciais e saldo não acessados. Teste simulado escrito, CI pendente. Não é homologação real; depende de execução autorizada no ambiente configurado.
