# Captação institucional #156

#155 mesclado, mas backend reprovou com 2 falhas e 261 aprovados (run 44341795873). A fixture Empresas0 era sobrescrita sem o varejista; importação local exigia token remoto desnecessariamente. Corrigidos sem relaxar validações. #154 teve três workflows aprovados. Railway seguia no #152 na consulta.

Coletor passa a identificar números brasileiros explicitamente rotulados como telefone, telefone comercial, SAC, central de atendimento ou financeiro em texto publicado, normaliza links tel nacionais, descarta links tel com letras e evita repetição de páginas na fila. Não infere WhatsApp a partir de telefone; continua exigindo links explícitos para redes sociais e WhatsApp. Preserva fonte e status de revisão existentes. Teste sintético escrito, CI pendente. Rótulo institucional não comprova titularidade nem alcance; números móveis podem pertencer a pessoas e exigem revisão. Não busca contatos pessoais deliberadamente.

Aceite real: selecionar sites oficiais confirmados de pequeno lote autorizado, verificar robots.txt e registrar páginas, canais extraídos e fontes, revisar titularidade e duplicidades antes da abordagem. Não houve captação externa real, alteração do banco produtivo ou envio de mensagens nesta revisão. A cobertura por canal e a quantidade real de empresas de Manaus continuam não confirmadas. Não habilita worker em produção.
