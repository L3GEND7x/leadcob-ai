# Staging nacional em disco

O módulo national_registry_stage prepara uma competência da Receita em SQLite
privado, sem acessar o PostgreSQL da aplicação. Lê os dez arquivos Empresas
e os dez Estabelecimentos uma vez cada em uma execução bem-sucedida. Registra
o progresso por arquivo, com transação atômica e inserções de 2.000 linhas
por vez. Falha em layout ou duplicidade interrompe e reverte o arquivo.
Em caso de interrupção, repete apenas o arquivo não confirmado.

```sh
cd backend
python -m app.jobs.national_registry_stage --stage /volume/privado/stage.sqlite --release AAAA-MM --local-dir /dados/privados --file Empresas0.zip
```

Use a competência oficial conferida, mesma pasta e arquivos imutáveis.
Repita para os vinte arquivos. --status informa progresso; --reconcile --uf AM
--part 0 exige os vinte completos e conta candidatos, sem identidade, excluídos
e elegíveis por junção. Não interpreta ausência como empresa baixada.
A política mantém marcadores mínimos para identificar raízes excluídas e não
armazena seus nomes ou capital. Não importa sócios, endereço, telefones,
e-mails ou nome fantasia. O banco intermediário ainda contém identificadores
e dados cadastrais de empresas: não publicar, não enviar a logs ou artefatos
públicos, restringir acesso, definir retenção e eliminar quando não necessário.

## Pré-requisitos de operação
Volume privado local persistente (diretório 0700, arquivo 0600 em POSIX),
escritor único, espaço medido para base, índices e journal; evitar rede
distribuída sem locking confiável. Não iniciar na Railway antes de estimar
custo. Este PR não cria infraestrutura, não executa captura real, não
transfere dados ao CRM e não agenda downloads. O banco de staging não
é prova de cobertura nacional: valida apenas o processamento dos arquivos.
Próximo passo: transferência paginada de registros conciliados para PostgreSQL
com preservação de CRM, supressão e controle de escrita concorrente.
