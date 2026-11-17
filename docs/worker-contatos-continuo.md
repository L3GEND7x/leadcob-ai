# Worker contínuo de contatos

Após homologar a fila, migrar o banco e validar recursos, executar um único processo dedicado no mesmo ambiente backend:

```sh
python -m app.jobs.discover_contacts --continuous --idle-seconds 15 --interval-seconds 2
```

O processo utiliza o banco configurado no ambiente, consulta somente itens existentes na fila e espera 15 segundos quando não há trabalho. Entre tentativas, aguarda 2 segundos por padrão. SIGTERM e SIGINT solicitam encerramento depois da tentativa corrente; interrupção forçada continua sujeita à recuperação de lease.

Não iniciar várias réplicas nesta primeira fase: os mecanismos existentes não garantem exatamente uma execução em caso de interrupção entre a coleta e a conclusão do item. Falhas de infraestrutura são registradas sem expor detalhes de credenciais e o loop espera antes de tentar novamente.

Para Railway: configurar um serviço separado com as mesmas variáveis de conexão, aplicar as migrações previamente e usar o comando acima como start command a partir do diretório backend. Conferir a política de reinício, logs, consumo e limites de rede. Não compartilhar segredos no repositório. Esta entrega não cria nem ativa o serviço Railway.

A fila precisa de alimentação explícita. Nenhum contato é enviado automaticamente. Antes de processar dezenas de milhares de empresas, validar uma amostra real, cobertura, custos e carga de rede.
