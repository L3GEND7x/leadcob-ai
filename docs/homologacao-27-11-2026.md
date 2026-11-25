# Homologação de entrega — 27/11/2026

Objetivo: entrega de uso interno assistido, sem falhas P0/P1 conhecidas, não
certificação de ausência absoluta de bugs. Acesso comercial multiempresa e
cobrança de assinaturas reais não devem ser habilitados sem homologação específica.
Não declarar a base nacional preenchida: os importadores estão em código;
a carga nacional depende de volume, infraestrutura, fonte e aprovação.

## Gates obrigatórios
1. CI verde na revisão consolidada: backend, integração PostgreSQL, benchmark,
   restauração sintética e navegador. Não usar o CI de um commit antigo.
2. Backup real recente, restore isolado comprovado e plano de rollback.
3. Deploy da revisão aprovada em Railway. O serviço estava fixado em
   b376f8778dfec2d15d7e7c2740f84c50fbda2b18 em 24/11; redeploy da build antiga
   não atualiza a versão. Selecionar revisão aprovada, preservar variáveis,
   PostgreSQL privado e migrações. Não ligar deploy contínuo sem gate.
4. Smoke anônimo com SHA esperado: executar o workflow manual **Verificação real da produção** na branch main, informando o SHA completo da versão implantada (deve coincidir com HEAD). O artefato agregado não contém credenciais. O workflow **Teste da implantação online** é um teste Docker isolado, não uma verificação da Railway. Alternativamente, executar localmente:
   PYTHONPATH=backend python -m app.jobs.release_smoke --base-url https://leadcob-web-production.up.railway.app --expected-sha SHA
5. Homologação autenticada pelo proprietário, em terminal local:
   PYTHONPATH=backend python -m app.jobs.owner_acceptance --expected-sha SHA
   A senha é solicitada sem eco; não copiar para chat, CI ou logs. O script
   valida revisão, sessão, contagens de Manaus, pesquisa, CRM, configuração
   da IA e schema; emite apenas resultados agregados. Não certifica provedor.
6. Testar no navegador desktop e celular: login/logout, filtros e páginas,
   detalhe real de empresa, contatos e fontes, central, CRM/tarefas, exportação.
   Conferir que contatos fictícios/ausentes não são exibidos como verificados.
7. Teste da IA com uma solicitação curta e orçamento previamente aprovado;
   conferir resposta baseada em ferramentas e erro de quota/modelo tratável.
8. Revisar dados reais da base, amostra de contatos institucionais e opt-out.
   Nenhum envio automático, faturamento real ou importação nacional maciça.
9. Registrar resultados, revisão, horário, responsável, defeitos e decisão
   de aceite. Se houver P0/P1, suspender a entrega operacional e corrigir.

## Limites desta homologação
Smoke autenticado não cria negócios, não envia mensagens e não aciona API paga.
Apenas login/logout alteram sessão. Os campos owner_release_ready e
provider_verified permanecem false por desenho. Uma conta de proprietário
não deve ser compartilhada com todos os integrantes do grupo; se necessário
homologar isolamento, permissões e contas comerciais antes de abrir acesso.
