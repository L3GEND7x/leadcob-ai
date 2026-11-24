# Smoke de produção externo

Workflow Producao — smoke externo anonimo: roda em pull requests que alteram o smoke, após push do workflow, execução manual e a cada seis horas. Sem credenciais, sem escrita, sem chamadas OpenAI, sem acesso financeiro. Verifica health, HTML/CSS/JS, anonimato da sessão comercial e bloqueios de acesso a páginas do proprietário. A CLI permite --expected-sha com commit aprovado em execuções controladas. Não substitui autorização com dois assinantes reais, conciliação financeira, worker em produção, recuperação de backup e LGPD.

A Railway pode estar fixada a um commit específico; push no GitHub não necessariamente atualiza produção automaticamente. Comparar SHA do deploy, verificar logs e só alterar o pin após homologação. Falhas deste job podem significar indisponibilidade pública ou bloqueio de rede do runner e exigem investigação.
## Ampliação de segurança — PR #174

Além dos nove acessos já verificados, o smoke externo passa a consultar anonimamente os endpoints de exportação CSV e de contactabilidade por CNPJ (11 verificações no total). O retorno esperado é **401 ou 403**, nunca arquivo CSV nem métrica privada. O workflow usa somente GET, não carrega cookies nem envia credenciais; não modifica registros ou aciona IA/coleta. Uma liberação indevida de qualquer rota faz o job falhar.

A verificação não certifica a qualidade dos dados, autorização entre diferentes organizações ou disponibilidade com login real. A versão em Railway pode estar fixada a um SHA anterior ao HEAD do GitHub; comparar explicitamente o commit implantado com a revisão aprovada. Não use hashes históricos da documentação como versão corrente.
