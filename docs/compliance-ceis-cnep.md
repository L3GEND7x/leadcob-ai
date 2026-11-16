# Alerta de conformidade CEIS/CNEP

A ficha da empresa pode consultar os registros públicos do **CEIS** e do **CNEP** pelo CNPJ da pessoa jurídica.

## Segurança e privacidade
- a chave fica somente em `PORTAL_TRANSPARENCIA_API_KEY`;
- a consulta envia somente o CNPJ da empresa da ficha;
- não são consultados CPF, nomes de sócios ou contatos pessoais;
- o valor da chave não é incluído em respostas ou logs do LeadCob.

## Interpretação
Um registro CEIS/CNEP é exibido como **alerta de conformidade**. Ele não é prova de inadimplência, não compõe
automaticamente o lead score e não deve ser usado sozinho como decisão de crédito ou de abordagem comercial.

## Estado
A integração está implementada e coberta por testes simulados. Até a proprietária cadastrar a chave e uma chamada
real ser validada, a fonte permanece **Planejada** no catálogo.
