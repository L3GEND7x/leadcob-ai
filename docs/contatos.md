# Contatos empresariais (v0.5.1; integrado na 0.5.2)

A aba **Contatos empresariais** mantém canais institucionais vinculados à empresa/CNPJ.

- `GET /api/contacts?q=&kind=&limit=&offset=`: lista paginada (até 500 por página).
- `POST /api/contacts`: adiciona canal com fonte declarada, evitando duplicidade.
- `POST /api/contacts/sync`: incorpora site/e-mail **já presentes** nas fichas; não acessa fontes externas.
- `PATCH /api/contacts/{id}/verify?status=verificado`: revisão humana.

**Limitação importante:** o coletor de CNPJ existente remove e-mail/telefone deliberadamente, porque podem pertencer a pessoas físicas. Esta versão **não faz enriquecimento autônomo externo com IA**. Uma etapa posterior poderá consultar sites institucionais autorizados com validação de domínio, finalidade, fonte e revisão, sem adivinhar dados. A lista de supressão impede exibição/sincronização dos contatos dessas empresas.

**Segurança:** a aplicação ainda não possui autenticação; não publique na internet sem implementar controle de acesso, HTTPS e política de retenção.
