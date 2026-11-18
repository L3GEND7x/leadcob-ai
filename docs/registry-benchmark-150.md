# Benchmark cadastral #150

#149 mesclado e três workflows aprovados. Benchmark executável em PostgreSQL dedicado local leadcob_test, schema aleatório descartável, sem usar DATABASE_URL da aplicação. Gera 53.000 CNPJs sintéticos com DV válido e 13.250 contatos sintéticos, todos identificados como fixtures, sem coleta ou comunicação externa. Testa inventário, classificação e lacunas de e-mail, conferindo contagens e paginação; aquecimento, cinco medições sequenciais e quatro consultas simultâneas por serviço. Relata mediana, máximo, tempos individuais, duração concorrente, RSS de pico e CPU do processo Python. CI publica JSON nos logs, resumo e artefato.

Executar a partir de backend com LEADCOB_TEST_POSTGRES_URL apontando para PostgreSQL local descartável leadcob_test: PYTHONPATH=. python benchmarks/registry_load.py. Nunca apontar para banco real. Não há SLA arbitrário: falhas de contagem ou execução reprovam o job; medir baseline antes de estabelecer metas. A configuração do CI limita a etapa a dez minutos.

Limites: não mede HTTP, latência de rede, CPU/RAM do PostgreSQL ou servidor produtivo, carga mista de assinantes, grandes duplicidades/supressões, dados heterogêneos, cache real, rate limit ou EXPLAIN ANALYZE. Não altera índices nem afirma capacidade produtiva. Teste escrito, execução e métricas pendentes do CI. Nenhum acesso à produção.
