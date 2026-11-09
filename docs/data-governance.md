# Governança e LGPD

Finalidade limitada à inteligência comercial B2B. Priorizar dados empresariais e canais institucionais. Não presumir que dado publicamente acessível pode ser reutilizado sem limites. Documentar base legal, finalidade, necessidade e salvaguardas para qualquer dado pessoal. Não coletar CPF, dados financeiros privados ou dados sensíveis para prospecção. Respeitar termos, APIs, robots.txt, limites e controles técnicos. Não contornar login, paywall, CAPTCHA ou bloqueios. Registrar origem, data, finalidade e prazo de revisão. Manter opt-out/lista de supressão. Abordagens em escala exigem aprovação humana. Diferenciar fatos de inferências: vaga aberta não prova intenção de terceirizar cobrança.


## Decisões registradas (09/11/2026)
- CNPJ: não importar sócios/QSA, e-mail, telefone ou endereço completo. Amostra real dos dados abertos mostrou e-mails pessoais de funcionários e contadores no campo de e-mail cadastral.
- Vagas: armazenar apenas dados da vaga e da empresa anunciante; nenhum dado de candidatos ou recrutadores.
- Concorrentes (CNAE 8291-1/00) são identificados e excluídos da prospecção por padrão.
- Empresário individual/MEI (natureza 213-5): excluído por padrão — razão social com nome + CPF em 70% da amostra real. Inclusão só com `--include-individual` e base legal documentada; o CPF é removido do nome.
- DataJud: só dados agregados (contagens), sem partes; nada identifica pessoas.
