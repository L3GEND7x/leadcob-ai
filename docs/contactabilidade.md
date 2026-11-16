# Mapa de contato e contactabilidade

## Objetivo
Transformar um lead identificado em um lead acionável sem importar dados pessoais desnecessários.

Cada empresa recebe um **score de contactabilidade de 0 a 100** baseado somente na cobertura de canais institucionais:
- e-mail institucional: até 25 pontos;
- telefone institucional: até 25;
- WhatsApp institucional: até 20;
- LinkedIn corporativo: até 10;
- site oficial: até 10;
- Instagram corporativo: até 5;
- Facebook corporativo: até 5.

Canal verificado recebe o peso integral; canal "a verificar" recebe 60% do peso. Canal inválido recebe zero.
O score mede **facilidade de contato**, não probabilidade de contratação, inadimplência ou qualidade do lead.

## Mapa de contato
A ficha mostra:
- canais institucionais priorizados;
- status e origem de cada canal;
- setores recomendados;
- setores já identificados;
- cargos/setores que vale procurar em fonte pública;
- lacunas ainda existentes;
- link de pesquisa pública para localizar o responsável pelo setor.

O sistema não armazena telefone pessoal, e-mail pessoal, CPF ou sócios.

## Enriquecimento
`POST /api/contacts/enrich/{id}`:
1. sincroniza site/e-mail institucional já presentes;
2. quando a busca Brave estiver configurada e não houver site, procura candidatos;
3. só confirma automaticamente um domínio quando houver **um único candidato com o CNPJ da empresa encontrado na própria página**;
4. lê o site cadastrado/confirmado respeitando `robots.txt`;
5. coleta apenas caixas institucionais e canais corporativos explícitos;
6. infere o setor somente por caixas funcionais como `licitacao@`, `financeiro@`, `cobranca@` e similares;
7. registra fonte e status para revisão.

Para órgãos públicos, domínios `.gov.br` podem aparecer como candidatos. Sem prova suficiente, continuam "a verificar".

## Setores sugeridos
Para sinais públicos:
- Licitações/Compras;
- Finanças;
- Administração.

Quando o objeto menciona cobrança, crédito, recebíveis, tributos ou finanças, Finanças sobe para a primeira prioridade.

Para empresas privadas:
- Cobrança/Crédito;
- Financeiro;
- Contas a Receber;
- Controladoria.

Essas são rotas comerciais sugeridas, não afirmações sobre a estrutura real da organização.
