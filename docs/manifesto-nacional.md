# Manifesto de execução nacional

O módulo national_registry_manifest organiza as 270 células UF × partição
de uma competência, começando pelo Amazonas. Guarda apenas metadados e contadores
em SQLite privado persistente. Não armazena contatos nem CNPJs no manifesto.

## Simulação padrão
cd backend
python -m app.jobs.national_registry_manifest --manifest /volume/preview.sqlite --release AAAA-MM --uf AM

Substitua AAAA-MM pela competência oficial validada. Por padrão executa uma célula.
Use --max-jobs 2 (máximo 10), somente com tempo e recursos suficientes. O filtro --uf
pode ser removido para seguir a ordem nacional. --status consulta sem importar.
O manifesto é vinculado à competência, modo, limite de candidatos e caminho local
dos arquivos; preserve a mesma configuração. Use arquivos imutáveis e da mesma competência.

## Falha e interrupção
- O processamento para na primeira falha. Próximo comando normal pula células failed.
- --retry-failed permite retomar falhas até três tentativas totais por célula.
- Um processo morto abruptamente pode deixar running; não há expiração automática.
- Só após comprovar que o processo terminou, use --uf AM --recover-part 0
  --confirm-process-stopped com a configuração original. Depois --retry-failed.
- Uma reserva por manifesto impede duas execuções simultâneas no mesmo SQLite.
  Não impede outros manifestos ou serviços concorrentes; não usar em volumes
  distribuídos sem garantias de locking.

## Gravação controlada
Somente após homologação do preview, backup restaurado, controle de orçamento
e janela exclusiva de escrita, crie um manifesto separado (apply.sqlite) e use
--apply --confirm-single-writer. Não habilitar cron antes desses requisitos.
O importador continua insert-only; em falha parcial, lotes já gravados podem
existir. Os totais do manifesto representam a última execução bem-sucedida de
cada célula, não um histórico exato de inserções nem contagem nacional única.

## Limitações
Não há scheduler, atualização de baixadas, staging nacional, reprocessamento de
células concluídas ou subdivisão municipal no manifesto. Uma célula grande que
exceda o limite exige revisão; não marque como concluída manualmente. O comando
de importação anterior suporta município, mas esses sublotes ainda não integram
o manifesto. Mesmo 270 células bem-sucedidas não comprovam cobertura oficial.
Status de produção e qualidade dos dados devem ser homologados separadamente.
