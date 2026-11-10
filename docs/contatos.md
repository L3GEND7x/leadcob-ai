# Contatos empresariais (v0.5.1; integrado na 0.5.2)

A aba **Contatos empresariais** mantém canais institucionais vinculados à empresa/CNPJ.

- `GET /api/contacts?q=&kind=&limit=&offset=`: lista paginada (até 500 por página).
- `POST /api/contacts`: adiciona canal com fonte declarada, evitando duplicidade.
- `POST /api/contacts/sync`: incorpora site/e-mail **já presentes** nas fichas; não acessa fontes externas.
- `PATCH /api/contacts/{id}/verify?status=verificado`: revisão humana.

**Limitação importante:** o coletor de CNPJ existente remove e-mail/telefone deliberadamente, porque podem pertencer a pessoas físicas. Esta versão **não faz enriquecimento autônomo externo com IA**. Uma etapa posterior poderá consultar sites institucionais autorizados com validação de domínio, finalidade, fonte e revisão, sem adivinhar dados. A lista de supressão impede exibição/sincronização dos contatos dessas empresas.

**Segurança:** a aplicação ainda não possui autenticação; não publique na internet sem implementar controle de acesso, HTTPS e política de retenção.

## Busca no site oficial (v0.5.3)
`POST /api/contacts/discover/{company_id}` lê o site institucional **já cadastrado e confirmado** na ficha. Não adivinha
domínios. Lê a página inicial e até 3 páginas de contato do mesmo domínio, respeitando robots.txt, sem login nem
formulários. Guarda só e-mails do próprio domínio com caixa institucional (contato@, financeiro@, comercial@, sac@...);
e-mails que parecem de pessoas (nome.sobrenome@) e de outros domínios são descartados. Cada contato registra a URL da
página de origem e entra como "a verificar".

Limite conhecido: o servidor precisa ter acesso de rede aos sites das empresas. No ambiente de nuvem usado para gerar a
página publicada esse acesso é bloqueado (ProxyError verificado em 10/11/2026); use a versão instalada ou cadastre o
contato à mão com a fonte.
