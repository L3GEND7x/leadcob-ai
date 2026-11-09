/* LeadCob AI 0.5 — interface por módulos (rotas #/modulo). Todos os dados vêm da API. */
const $ = id => document.getElementById(id);
const V = () => $('view');

async function api(path, opt = {}) {
  const r = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...opt });
  if (!r.ok) { const e = Error(await r.text()); e.status = r.status; throw e; }
  return r.json();
}
const send = (path, method, body) => api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

// ------------------------------------------------------------------ utilidades
function esc(x) {
  return String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function errMsg(e, fallback = 'Não foi possível concluir.') {
  try {
    const d = JSON.parse(e.message).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map(x => `${(x.loc || []).slice(-1)[0] || ''}: ${x.msg}`).join('; ');
  } catch (_) {}
  return fallback;
}
const fmt = n => (n ?? 0).toLocaleString('pt-BR');
const money = v => (v || v === 0) && v !== '' ? Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : '';
const when = iso => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); };
const day = iso => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString('pt-BR'); };
const today = () => new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
const loc = s => [s.city, s.state].filter(Boolean).join(' / ') || 'UF não informada';
const pill = (score, band, label) => `<span class="pill ${esc(band)}" title="${esc(label || '')}">${score}</span>`;
const natCls = s => { s = String(s || '').toLowerCase(); return s.startsWith('fato') ? 'fato' : s.startsWith('indício') || s.startsWith('indicio') ? 'indicio' : 'hipotese'; };
const head = (eb, t, sub = '', act = '') => `<div class="pagehead"><div><small>${eb}</small><h1>${t}</h1>${sub ? `<p>${sub}</p>` : ''}</div>${act ? `<div class="actions">${act}</div>` : ''}</div>`;
const panel = (title, sub, body, cls = '') => `<article class="panel ${cls}"><h2>${title}</h2>${sub ? `<p class="note" style="margin:-6px 0 8px">${sub}</p>` : ''}${body}</article>`;
const toLocalInput = iso => { if (!iso) return ''; const d = new Date(iso); if (isNaN(d)) return ''; const p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
const fromLocalInput = v => v ? new Date(v).toISOString() : null;
const PUBLISHED = typeof LC !== 'undefined';

function toast(t, ms = 4000, err = false) {
  const el = $('toast'); el.textContent = t; el.className = err ? 'err' : ''; el.style.display = 'block';
  clearTimeout(toast._t); toast._t = setTimeout(() => el.style.display = 'none', ms);
}
async function copyText(btn) {
  try { await navigator.clipboard.writeText(btn.dataset.t); toast('Texto copiado. Revise antes de enviar.'); }
  catch (_) { toast('Não foi possível copiar automaticamente: selecione o texto e copie.', 5000, true); }
}
function coRow(s, extra = '') {
  return `<a class="row" href="#/empresa/${s.id}">${pill(s.score, s.band, s.band_label)}<div class="main"><strong>${esc(s.name)}</strong>`
    + `<small>${esc(loc(s))} · ${esc(s.profile_label || s.segment || 'setor não identificado')} · ${esc(s.stage_label)}${extra ? ' · ' + extra : ''}</small></div></a>`;
}
const rows = (items, emptyMsg, extra) => items.length ? `<div class="rows">${items.map(s => coRow(s, extra ? esc(extra(s)) : '')).join('')}</div>` : `<p class="empty">${emptyMsg}</p>`;

// ------------------------------------------------------------------ rotas
const ROUTES = { inicio: viewInicio, hoje: viewHoje, empresas: viewEmpresas, sinais: viewSinais, crm: viewCRM,
  empresa: viewEmpresa, radar: viewRadar, fontes: viewFontes, config: viewConfig };
let CUR = { v: 'inicio', arg: null };
async function route() {
  const [v, arg] = location.hash.replace(/^#\/?/, '').split('/');
  CUR = { v: ROUTES[v] ? v : 'inicio', arg: arg ? decodeURIComponent(arg) : null };
  const navKey = CUR.v === 'empresa' ? 'crm' : CUR.v;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.v === navKey));
  try { await ROUTES[CUR.v](CUR.arg); }
  catch (e) { console.error(e); V().innerHTML = head('Erro', 'Não foi possível abrir esta tela', esc(errMsg(e, 'A API não respondeu.'))); }
}
// chamada pela camada da página publicada quando os dados mudam; não apaga o que está sendo digitado
function load() {
  const a = document.activeElement;
  if (a && V().contains(a) && /INPUT|TEXTAREA|SELECT/.test(a.tagName)) return;
  route();
}
window.addEventListener('hashchange', () => { window.scrollTo(0, 0); route(); });

// ------------------------------------------------------------------ central de comando
async function viewInicio() {
  const d = await api('/command-center'), k = d.kpis;
  const kp = (label, val, sub, cls = '') => `<article class="${cls}"><small>${label}</small><strong>${val}</strong><span>${sub}</span></article>`;
  const overdue = d.followups_atrasados.length ? `<div class="rows">${d.followups_atrasados.map(x => `<a class="row" href="${x.company_id ? '#/empresa/' + x.company_id : '#/crm'}"><span class="pill nao_contatar">!</span><div class="main"><strong>${esc(x.company_name || 'Sem empresa')}</strong><small>${esc(x.title)} · venceu em ${when(x.due_at)}</small></div></a>`).join('')}</div>`
    : '<p class="empty">Nada atrasado.</p>';
  const recent = d.oportunidades_recentes.length ? `<div class="rows">${d.oportunidades_recentes.map(o => `<a class="row" href="#/empresa/${o.company_id}"><span class="tag ${esc(o.kind)}">${o.kind === 'public_procurement' ? 'EDITAL' : o.kind === 'hiring' ? 'VAGA' : 'SINAL'}</span><div class="main"><strong>${esc(o.company_name)}</strong><small>${esc(o.title)} · ${esc(o.source)} · ${day(o.captured_at)}</small></div></a>`).join('')}</div>`
    : '<p class="empty">Nenhum sinal captado ainda. Use “Sinais e oportunidades” para buscar editais e vagas.</p>';
  const tasks = d.tarefas_pendentes.length ? `<div class="rows">${d.tarefas_pendentes.map(t => `<a class="row" href="${t.company_id ? '#/empresa/' + t.company_id : '#/crm'}"><span class="pill">☐</span><div class="main"><strong>${esc(t.title)}</strong><small>${esc(t.company_name || '')}${t.due_at ? ' · até ' + when(t.due_at) : ' · sem prazo'}</small></div></a>`).join('')}</div>`
    : '<p class="empty">Nenhuma tarefa pendente.</p>';
  V().innerHTML = head('Operação diária · ' + esc(today()), 'Central de comando', 'Quem abordar, quem cobrar resposta e o que mudou na base. Tudo calculado sobre os dados do banco.',
    '<a class="btn primary" href="#/hoje">✦ Inteligência do dia</a><a class="btn" href="#/empresas">⌕ Encontrar empresas</a>')
    + `<section class="kpis">${[
      kp('Empresas na base', fmt(k.empresas_total), `${fmt(k.empresas_novas_hoje)} nova(s) hoje`),
      kp('Sinais novos hoje', fmt(k.oportunidades_novas_hoje), 'editais, vagas e cadastros'),
      kp('Leads qualificados', fmt(k.leads_qualificados), 'de “Qualificada” em diante'),
      kp('Não abordados', fmt(k.leads_nao_abordados), 'qualificados ou prontos'),
      kp('Contatos realizados', fmt(k.contatos_realizados), 'empresas contatadas'),
      kp('Respostas', fmt(k.respostas), 'empresas que responderam'),
      kp('Reuniões', fmt(k.reunioes), 'empresas com reunião'),
      kp('Propostas', fmt(k.propostas), 'empresas com proposta'),
      kp('Contratos', fmt(k.contratos), 'clientes conquistados', 'accent'),
      kp('Conversão', k.taxa_conversao == null ? '—' : k.taxa_conversao.toLocaleString('pt-BR') + '%', 'contratos ÷ contatadas'),
      kp('Valor potencial', k.valor_potencial ? money(k.valor_potencial) : '—', 'soma do que você informou'),
    ].join('')}</section>`
    + `<h2>Funil comercial</h2><div class="funnel">${d.pipeline.map(p => `<a href="#/crm" class="${['perdido', 'nao_contatar', 'acompanhar_futuramente'].includes(p.key) ? 'closed' : ''}"><b>${fmt(p.count)}</b><span>${esc(p.label)}</span></a>`).join('')}</div>`
    + `<div class="grid2">
      ${panel('Precisam de abordagem', 'Qualificadas ou prontas, ainda sem contato', rows(d.precisam_abordagem, 'Nenhuma empresa marcada como qualificada ou pronta. Comece pela Inteligência do dia.'))}
      ${panel('Follow-ups atrasados', 'Tarefas e próximas atividades vencidas', overdue)}
      ${panel('Maior pontuação', 'Empresas em aberto com maior prioridade', rows(d.maior_pontuacao, 'Sem empresas na base.'))}
      ${panel('Novos sinais (7 dias)', 'Empresas com edital, vaga ou cadastro recente', rows(d.novos_sinais, 'Nenhum sinal novo nesta semana.', s => 'sinal em ' + day(s.last_signal_at)))}
      ${panel('Sinais recentes', 'Últimas oportunidades captadas, com fonte', recent)}
      ${panel('Tarefas pendentes', 'Em dia', tasks)}
    </div>
    <p class="note">Listas calculadas sobre ${fmt(d.base_avaliada)} empresas (com sinal, no funil ou de maior capital). ${esc(k.notas.valor_potencial)} ${esc(k.notas.taxa_conversao)}</p>`;
}

// ------------------------------------------------------------------ inteligência do dia
async function viewHoje() {
  const d = await api('/daily-intelligence?limit=5');
  V().innerHTML = head('Inteligência do dia · ' + esc(today()), 'Cinco empresas para trabalhar hoje',
    'Escolhidas por regras explicáveis. Cada item separa o que é fato (fonte registrada), indício e hipótese comercial.',
    '<button onclick="route()">↻ Recalcular</button>')
    + (d.itens.length ? `<div class="cards">${d.itens.map(card).join('')}</div>`
      : panel('Nenhuma empresa elegível agora', '', '<p class="empty">Todas as empresas da base estão encerradas, na lista de supressão ou foram contatadas há pouco. Busque novas empresas em “Encontrar empresas” ou capte sinais.</p>'))
    + `<p class="note">${esc(d.metodo)} Gerado em ${when(d.gerado_em)}.</p>`;
}
function card(x, i) {
  const ev = x.evidencia;
  const evid = ev.url ? `<a class="src" href="${esc(ev.url)}" target="_blank" rel="noopener">${esc(ev.titulo)}</a> · ${esc(ev.fonte || '')} · captada em ${day(ev.captada_em)} <span class="nat fato">fato</span>`
    : `${esc(ev.titulo)} <span class="nat ${natCls(ev.natureza)}">${esc(ev.natureza)}</span>`;
  const list = (t, cls, arr) => `<div><span class="nat ${cls}">${t}</span>${arr.length ? `<ul>${arr.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : '<p class="note">Nenhum.</p>'}</div>`;
  return `<article class="card"><header><div><span class="rank">${i + 1}</span><h2>${esc(x.name)}</h2>
      <div class="facts-line"><span>${esc(x.cnpj_formatted || 'sem CNPJ')}</span><span>${esc(loc(x))}</span><span>${esc(x.profile_label || x.segment || 'setor não identificado')}</span><span>${esc(x.stage_label)}</span></div></div>
      <div class="bigscore">${pill(x.score, x.band, x.band_label)}<small>${esc(x.band_label)}</small></div></header>
    <dl><dt>Por que hoje</dt><dd>${esc(x.motivo)}</dd>
      <dt>Evidência</dt><dd>${evid}</dd>
      <dt>Serviço sugerido</dt><dd>${esc(x.servico)} <small class="muted">(${esc(x.servico_natureza)})</small></dd>
      <dt>Como iniciar</dt><dd><div class="quote">${esc(x.abertura)}</div><button class="small" style="margin-top:6px" data-t="${esc(x.abertura)}" onclick="copyText(this)">⧉ Copiar texto</button></dd>
      <dt>Canal</dt><dd>${esc(x.canal)}</dd>
      <dt>Próxima ação</dt><dd>${esc(x.proxima_acao)}</dd></dl>
    <div class="facts">${list('Fatos', 'fato', x.fatos)}${list('Indícios', 'indicio', x.indicios)}${list('Hipóteses', 'hipotese', x.hipoteses)}</div>
    <div class="warnbox">⚠ ${esc(x.cuidado)}</div>
    <div class="actions" style="margin-top:12px"><a class="btn primary" href="#/empresa/${x.id}">Abrir ficha e registrar contato</a></div></article>`;
}

// ------------------------------------------------------------------ encontrar empresas
const F = { sort: 'score', page: 1, per_page: 25 };
let LOOKUPS = null;
async function lookups() {
  if (!LOOKUPS) {
    const [segs, debts, regions] = await Promise.all([api('/segments').catch(() => []), api('/debt-types').catch(() => []), api('/regions').catch(() => ({}))]);
    LOOKUPS = { segs, debts, regions };
  }
  return LOOKUPS;
}
const STAGE_OPTS = [['identificada', 'Empresa identificada'], ['em_pesquisa', 'Em pesquisa'], ['qualificada', 'Qualificada'], ['pronta_abordagem', 'Pronta para abordagem'],
  ['primeiro_contato', 'Primeiro contato realizado'], ['aguardando_resposta', 'Aguardando resposta'], ['em_negociacao', 'Em negociação comercial'], ['reuniao_agendada', 'Reunião agendada'],
  ['proposta_enviada', 'Proposta enviada'], ['cliente_conquistado', 'Cliente conquistado'], ['perdido', 'Perdido'], ['acompanhar_futuramente', 'Acompanhar futuramente'], ['nao_contatar', 'Não contatar']];
const UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'];
const opts = (pairs, cur, empty) => (empty !== undefined ? `<option value="">${empty}</option>` : '') + pairs.map(([v, l]) => `<option value="${esc(v)}" ${String(cur ?? '') === String(v) ? 'selected' : ''}>${esc(l)}</option>`).join('');

async function viewEmpresas() {
  const L = await lookups();
  const inp = (k, ph, type = 'text') => `<input data-f="${k}" type="${type}" placeholder="${ph}" value="${esc(F[k] ?? '')}">`;
  const sel = (k, pairs, empty) => `<select data-f="${k}">${opts(pairs, F[k], empty)}</select>`;
  V().innerHTML = head('Prospecção nacional', 'Encontrar empresas',
    'Todos os setores, portes e UFs da base. Cadastro não comprova demanda: a pontuação mostra o que é fato e o que é hipótese.',
    '<button class="primary" onclick="$(\'dlg-company\').showModal()">＋ Adicionar empresa</button><button onclick="exportCSV()">⇩ Exportar CSV</button>')
    + `<div class="panel" style="margin-bottom:12px"><div class="filters">
        ${inp('q', 'Razão social, fantasia ou CNPJ')}
        ${sel('region', Object.keys(L.regions).map(r => [r, r]), 'Todas as regiões')}
        ${inp('uf', 'UF(s): AM,PA')}
        ${inp('municipio', 'Município')}
        ${sel('profile', L.segs.map(s => [s.key, s.label]), 'Todos os perfis')}
        ${sel('sort', [['score', 'Ordenar: pontuação'], ['capital', 'Ordenar: capital social'], ['name', 'Ordenar: nome'], ['opened', 'Ordenar: mais antigas'], ['recent', 'Ordenar: sinal mais recente']])}
      </div>
      <details class="more" ${['cnae', 'debt_type', 'size', 'situacao', 'capital_min', 'capital_max', 'years_min', 'years_max', 'stage', 'band', 'has_signal'].some(k => F[k]) ? 'open' : ''}><summary>Mais filtros</summary><div class="filters">
        ${inp('cnae', 'CNAE (ex.: 4639 ou 8630501)')}
        ${sel('debt_type', L.debts.map(d => [d.key, d.label]), 'Todos os tipos de inadimplência')}
        ${sel('size', [['MICRO EMPRESA', 'Microempresa'], ['EMPRESA DE PEQUENO PORTE', 'Pequeno porte'], ['DEMAIS', 'Demais (acima de EPP)']], 'Todos os portes')}
        ${sel('situacao', [['ATIVA', 'Ativa'], ['BAIXADA', 'Baixada'], ['INAPTA', 'Inapta'], ['SUSPENSA', 'Suspensa'], ['NULA', 'Nula']], 'Qualquer situação')}
        ${inp('capital_min', 'Capital mínimo (R$)', 'number')}${inp('capital_max', 'Capital máximo (R$)', 'number')}
        ${inp('years_min', 'Anos de atividade (mín.)', 'number')}${inp('years_max', 'Anos de atividade (máx.)', 'number')}
        ${sel('stage', STAGE_OPTS, 'Qualquer etapa')}
        ${sel('band', [['alta', 'Prioridade alta (80–100)'], ['intermediaria', 'Intermediária (60–79)'], ['pesquisar', 'Pesquisar melhor (40–59)'], ['baixa', 'Baixa (0–39)']], 'Qualquer faixa')}
        ${sel('has_signal', [['true', 'Com sinal captado'], ['false', 'Sem sinal']], 'Com ou sem sinal')}
        <label class="check"><input type="checkbox" data-f="include_competitors" ${F.include_competitors ? 'checked' : ''}> Incluir concorrentes (CNAE 8291)</label>
      </div></details>
      <div class="actions"><button onclick="clearFilters()">Limpar filtros</button></div></div>
      <div id="res"><p class="note">Buscando…</p></div>`;
  V().querySelectorAll('[data-f]').forEach(el => el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', () => {
    F[el.dataset.f] = el.type === 'checkbox' ? el.checked : el.value.trim(); F.page = 1;
    clearTimeout(viewEmpresas._t); viewEmpresas._t = setTimeout(searchCompanies, 300);
  }));
  searchCompanies();
}
function clearFilters() { Object.keys(F).forEach(k => delete F[k]); Object.assign(F, { sort: 'score', page: 1, per_page: 25 }); viewEmpresas(); }
function goPage(n) { F.page = n; searchCompanies(); $('res').scrollIntoView({ behavior: 'smooth' }); }
async function searchCompanies() {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(F)) if (v !== '' && v != null && v !== false) p.set(k, v);
  const box = $('res'); if (!box) return;
  try {
    const d = await api('/companies/search?' + p);
    const from = d.total ? (d.page - 1) * d.per_page + 1 : 0, to = (d.page - 1) * d.per_page + d.items.length;
    box.innerHTML = `<div class="tablebox"><table><thead><tr><th>Empresa</th><th>Localização</th><th>Perfil / CNAE</th><th>Porte / capital</th><th>Atividade</th><th>Sinais</th><th>Etapa</th><th>Pontuação</th></tr></thead><tbody>
      ${d.items.length ? d.items.map(c => `<tr>
        <td><a class="name" href="#/empresa/${c.id}"><strong>${esc(c.name)}</strong></a><small>${esc(c.cnpj_formatted || 'sem CNPJ')}${c.trade_name ? ' · ' + esc(c.trade_name) : ''}</small>${c.registration_status && c.registration_status !== 'ATIVA' ? `<div class="badges"><span class="badge bad">${esc(c.registration_status)}</span></div>` : ''}</td>
        <td>${esc(loc(c))}<small>${esc(c.region || '')}</small></td>
        <td>${esc(c.profile_label || c.segment || '—')}<small>${esc(c.cnae_main || '')} ${esc(c.cnae_desc || '')}</small></td>
        <td>${esc(c.company_size || '—')}<small>${money(c.capital_social)}</small></td>
        <td>${c.years_active != null ? `${c.years_active.toLocaleString('pt-BR')} anos` : '—'}<small>${c.opened_at ? 'desde ' + esc(c.opened_at.split('-').reverse().join('/')) : ''}</small></td>
        <td>${c.signals ? `<span class="badge ok">${c.signals}</span><small>${day(c.last_signal_at)}</small>` : '<small>nenhum</small>'}</td>
        <td>${esc(c.stage_label)}</td>
        <td>${pill(c.score, c.band, c.band_label)}<small>${esc(c.band_label)}</small></td></tr>`).join('')
      : '<tr><td colspan="8">Nenhuma empresa com esses filtros. Amplie a busca ou importe a base de CNPJ da UF (job em lote).</td></tr>'}
      </tbody></table></div>
      <div class="pager"><span class="note">${d.total ? `Mostrando ${fmt(from)}–${fmt(to)} de ${fmt(d.total)}` : 'Nenhum resultado'}${d.note ? ' · ' + esc(d.note) : ''}</span>
        <span class="actions"><button class="small" ${d.page <= 1 ? 'disabled' : ''} onclick="goPage(${d.page - 1})">← Anterior</button><button class="small" ${to >= d.total ? 'disabled' : ''} onclick="goPage(${d.page + 1})">Próxima →</button></span></div>`;
  } catch (e) { box.innerHTML = `<p class="note">${esc(errMsg(e, 'Falha na busca.'))}</p>`; }
}
function exportCSV() {
  if (PUBLISHED) return toast('A exportação em CSV funciona na versão instalada (servidor próprio).', 6000, true);
  const p = new URLSearchParams();
  if (F.uf) p.set('uf', F.uf); if (F.profile) p.set('profile', F.profile); if (F.stage) p.set('stage', F.stage);
  location.href = '/api/export/companies.csv?' + p;
}
$('companyform').addEventListener('submit', async e => {
  e.preventDefault();
  const d = Object.fromEntries([...new FormData(e.target).entries()].filter(([, v]) => v.trim() !== ''));
  try {
    const r = await send('/companies', 'POST', d);
    $('dlg-company').close(); e.target.reset(); toast('Empresa adicionada.'); location.hash = '#/empresa/' + r.id;
  } catch (err) { toast(errMsg(err, 'Não foi possível adicionar; revise os campos.'), 7000, true); }
});

// ------------------------------------------------------------------ sinais e oportunidades (editais, vagas, cadastros)
let data = [];
const KIND = { hiring: 'VAGA / CONTRATAÇÃO', public_procurement: 'EDITAL PÚBLICO', outsourcing: 'POSSÍVEL TERCEIRIZAÇÃO' };
const STATUS = { qualified: 'QUALIFICADO', discarded: 'DESCARTADO', review: 'EM ANÁLISE' };
const CLASS = {
  edital_aberto: ['EDITAL ABERTO', 'ok'], edital_encerrado: ['PRAZO ENCERRADO', 'bad'],
  contratacao_direta: ['CONTRATAÇÃO DIRETA', 'warn'], prazo_nao_informado: ['PRAZO NÃO INFORMADO', 'warn'],
  operacao_interna: ['EQUIPE PRÓPRIA DE COBRANÇA', 'ok'], estrategia_dados: ['ÁREA DE RECUPERAÇÃO ESTRUTURADA', 'ok'],
  vaga_encerrada: ['VAGA ENCERRADA', 'bad'], concorrente: ['CONCORRENTE', 'bad'],
};
const REL = { alta: ['ADERÊNCIA ALTA', 'ok'], revisar: ['ADERÊNCIA A REVISAR', 'warn'], descartar: ['FORA DO ESCOPO', 'bad'] };
const EVID = { confirmada_api_oficial: ['API OFICIAL', 'ok'], indicio_busca: ['SÓ ÍNDICE DE BUSCA', 'warn'], fonte_primaria: ['API DO BOARD', 'ok'] };
const badge = (map, key) => map[key] ? `<span class="badge ${map[key][1]}">${map[key][0]}</span>` : '';

async function viewSinais() {
  if (!$('rows')) {
    V().innerHTML = head('Prospecção · fontes públicas', 'Sinais e oportunidades',
      'Editais (PNCP), vagas de cobrança (Greenhouse/Lever) e sinais cadastrados por você. Só é “comprovada” a oportunidade com edital aberto, aderente e confirmado na API oficial.',
      '<button class="capture" id="capture-pncp" onclick="capturePNCP()">⌕ Buscar editais PNCP</button><button class="capture" id="capture-jobs" onclick="captureJobs()">↗ Buscar vagas públicas</button><button class="primary" onclick="$(\'dlg-opp\').showModal()">＋ Nova oportunidade</button>')
      + `<section class="kpis" id="opp-kpis"></section>
      <div class="filters inline"><input id="search" placeholder="Buscar empresa ou título..." oninput="render()">
        <select id="kind" onchange="render()"><option value="">Todas as frentes</option><option value="hiring">Vagas de cobrança</option><option value="outsourcing">Terceirização</option><option value="public_procurement">Editais públicos</option></select>
        <select id="status" onchange="load()"><option value="">Todos os status</option><option value="review">Em análise</option><option value="qualified">Qualificado</option><option value="discarded">Descartado</option></select>
        <select id="signal" onchange="render()"><option value="">Comprovadas e sinais</option><option value="oportunidade_comprovada">Só comprovadas</option><option value="sinal_a_confirmar">Só sinais a confirmar</option></select></div>
      <div class="tablebox"><table><thead><tr><th>Empresa / oportunidade</th><th>Frente</th><th>Localização</th><th>Origem / prazo</th><th>Score</th><th>Status</th><th></th></tr></thead><tbody id="rows"><tr><td colspan="7">Carregando…</td></tr></tbody></table></div>
      <div class="grid2" style="margin-top:14px">${panel('Pipeline de agentes', 'Rode pelo botão ↗ de cada linha', `<div class="rows">
        <div class="row"><span class="pill">01</span><div class="main"><strong>Pesquisa</strong><small>Confere fonte, URL e evidência registradas</small></div></div>
        <div class="row"><span class="pill">02</span><div class="main"><strong>Qualificação</strong><small>Pontua o sinal; editais e vagas captados mantêm a pontuação do classificador</small></div></div>
        <div class="row"><span class="pill">03</span><div class="main"><strong>Auditoria</strong><small>Lista o que falta confirmar (edital, prazo, interesse em terceirizar)</small></div></div>
        <div class="row"><span class="pill">04</span><div class="main"><strong>Supervisor</strong><small>Orquestra e exige revisão humana</small></div></div></div><div id="lastrun" class="note"></div>`)}
        ${panel('Como ler', '', `<p class="note">Edital público não é oportunidade privada: a contratação segue a lei de licitações e o edital. Vaga de cobrança mostra que a empresa estrutura a área, mas não comprova interesse em terceirizar. Nenhum sinal desta tela prova que a empresa tem inadimplência.</p>`)}</div>`;
  }
  const status = $('status').value;
  const [s, list] = await Promise.all([api('/dashboard/summary'), api('/opportunities' + (status ? `?status=${status}` : ''))]);
  data = list;
  const kp = (l, v, sub, cls = '') => `<article class="${cls}"><small>${l}</small><strong>${fmt(v)}</strong><span>${sub}</span></article>`;
  $('opp-kpis').innerHTML = kp('Sinais mapeados', s.total, 'base atual') + kp('Vagas de cobrança', s.hiring, 'empresas contratando')
    + kp('Editais públicos', s.public_procurement, 'PNCP') + kp('Comprovadas', s.proven, 'edital aberto · aderente · API oficial', 'accent')
    + kp('A confirmar', s.to_confirm, `qualificados: ${fmt(s.qualified)} · score médio ${s.average_score}`);
  render(); lastRun();
}
function render() {
  if (!$('rows')) return;
  const q = $('search').value.toLowerCase(), k = $('kind').value, st = $('status').value, sg = $('signal').value;
  const a = data.filter(x => (!q || (x.company_name + ' ' + x.title).toLowerCase().includes(q)) && (!k || x.kind === k)
    && (!st || x.status === st) && (!sg || x.commercial_signal === sg));
  $('rows').innerHTML = a.length ? a.map(x => {
    const proc = x.kind === 'public_procurement' || !!x.evidence_level;
    const badges = proc ? `<div class="badges">${x.commercial_signal === 'oportunidade_comprovada' ? '<span class="badge ok">✓ COMPROVADA</span>' : '<span class="badge warn">SINAL A CONFIRMAR</span>'}${badge(CLASS, x.opportunity_class)}${badge(REL, x.relevance)}${badge(EVID, x.evidence_level)}</div>` : '';
    const why = proc && x.relevance_reason ? `<span class="why">${esc(x.relevance_reason)}</span>` : '';
    const src = x.source_url ? `<a class="src" href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_name)}</a>` : esc(x.source_name);
    const extra = [x.modality_name, money(x.estimated_value)].filter(Boolean).map(esc).join(' · ');
    const dl = x.deadline ? `<span class="deadline">Propostas até ${when(x.deadline)}</span>` : '';
    const name = x.company_id ? `<a class="name" href="#/empresa/${x.company_id}"><strong>${esc(x.company_name)}</strong></a>` : `<strong>${esc(x.company_name)}</strong>`;
    return `<tr><td>${name}<small>${esc(x.title)}</small>${badges}${why}</td>
      <td><span class="tag ${esc(x.kind)}">${KIND[x.kind] || esc(x.kind)}</span></td>
      <td>${esc([x.city, x.state].filter(Boolean).join(' / ') || '—')}</td>
      <td>${src}${extra ? `<span class="deadline">${extra}</span>` : ''}${dl}</td>
      <td><span class="score" title="${esc(x.score_reason)}">${x.score}/100</span></td>
      <td><span class="status ${esc(x.status)}">${STATUS[x.status] || 'EM ANÁLISE'}</span></td>
      <td><button class="action" title="Executar agentes" onclick="runAgents(${x.id})">↗</button></td></tr>`;
  }).join('') : '<tr><td colspan="7">Nenhuma oportunidade encontrada.</td></tr>';
}
async function runAgents(id) {
  try {
    const r = await api(`/agents/run/${id}`, { method: 'POST' });
    const issues = r.agents.audit.issues.length ? ` · ${r.agents.audit.issues.length} alerta(s) de auditoria` : '';
    toast(`Agentes concluídos · score ${r.opportunity.score}/100${issues}`); viewSinais();
  } catch (e) { toast(errMsg(e, 'Falha ao executar agentes.'), 8000, true); }
}
async function lastRun() {
  try {
    const runs = await api('/capture/runs');
    if (!$('lastrun')) return;
    if (!runs.length) { $('lastrun').textContent = 'Nenhuma captação executada ainda.'; return; }
    const r = runs[0];
    $('lastrun').textContent = `Última captação (${when(r.started_at)}): ${r.status} — ${r.message}`;
  } catch (e) { /* tela continua funcional */ }
}
async function capturePNCP() {
  const btn = $('capture-pncp');
  btn.disabled = true; btn.textContent = 'Consultando PNCP… (1–3 min)';
  try {
    const r = await api('/capture/pncp?mode=busca&max_pages=2', { method: 'POST' });
    const partial = r.fallback ? ' · a busca do portal não respondeu; usada a API oficial (cobertura menor)'
      : r.status === 'partial' ? ` · ${r.errors.length} consulta(s) falharam — repita mais tarde` : '';
    toast(`PNCP: ${r.found} encontrados · ${r.discarded} descartados por aderência · ${r.proven} comprovadas · ${r.to_confirm} sinais a confirmar · ${r.created} novos${partial}`, 9000);
    await viewSinais();
  } catch (e) {
    toast(errMsg(e, 'O PNCP não respondeu (a API limita rajadas de consultas). Tente novamente em alguns minutos.'), 9000, true); lastRun();
  } finally { btn.disabled = false; btn.textContent = '⌕ Buscar editais PNCP'; }
}
async function captureJobs() {
  const btn = $('capture-jobs');
  btn.disabled = true; btn.textContent = 'Consultando boards…';
  try {
    const r = await api('/capture/jobs', { method: 'POST' });
    toast(`Vagas: ${r.jobs_read} lidas em ${r.boards_fetched} boards · ${r.matches} aderentes · ${r.created} novas · ${r.closed} encerradas · ${r.competitors} de concorrentes${r.errors.length ? ` · ${r.errors.length} board(s) com falha` : ''}`, 9000);
    await viewSinais();
  } catch (e) { toast(errMsg(e, 'Falha ao consultar vagas.'), 8000, true); }
  finally { btn.disabled = false; btn.textContent = '↗ Buscar vagas públicas'; }
}
$('newform').addEventListener('submit', async e => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target).entries());
  try {
    await api('/opportunities', { method: 'POST', body: JSON.stringify(d) });
    $('dlg-opp').close(); e.target.reset(); toast('Oportunidade cadastrada.'); if (CUR.v === 'sinais') viewSinais();
  } catch (err) { toast(errMsg(err, 'Não foi possível salvar; revise os campos.'), 7000, true); }
});
async function fillFromCNPJ() {
  const f = $('newform'), v = $('form-cnpj').value;
  try {
    const d = await api('/cnpj/' + encodeURIComponent(v.replace(/[^0-9A-Za-z]/g, '')));
    f.company_name.value = d.razao_social || f.company_name.value;
    f.segment.value = d.cnae_descricao || f.segment.value;
    f.city.value = d.municipio || f.city.value; f.state.value = d.uf || f.state.value;
    toast(`${d.razao_social} · ${d.situacao_cadastral} · fonte: ${d.source}`);
  } catch (e) { toast(errMsg(e, 'CNPJ não localizado.'), 6000, true); }
}

// ------------------------------------------------------------------ CRM comercial
async function viewCRM() {
  const [p, tasks] = await Promise.all([api('/pipeline'), api('/tasks?status=open')]);
  const col = st => `<div class="col"><h3>${esc(st.label)} <span>${fmt(st.count)}</span></h3>${st.key === 'identificada'
    ? `<p class="note">Empresas da base ainda não trabalhadas. Abra uma ficha e mude a etapa para tirá-la daqui.</p><a class="btn small" href="#/empresas">⌕ Encontrar empresas</a>`
    : st.items.length ? st.items.map(s => `<a class="mini" href="#/empresa/${s.id}"><strong>${esc(s.name)}</strong><small>${pill(s.score, s.band, s.band_label)} ${esc(loc(s))}</small>${s.next_action ? `<small>▸ ${esc(s.next_action)}${s.next_action_at ? ' · ' + when(s.next_action_at) : ''}</small>` : ''}</a>`).join('')
      : '<p class="note">Vazio.</p>'}</div>`;
  const now = Date.now();
  V().innerHTML = head('Relacionamento comercial', 'CRM comercial', 'Funil de 13 etapas. Para mover uma empresa, abra a ficha: cada mudança fica registrada no histórico e na auditoria.',
    '<button class="primary" onclick="$(\'dlg-company\').showModal()">＋ Adicionar empresa</button>')
    + `<div class="board">${p.stages.map(col).join('')}</div>`
    + `<div class="grid2" style="margin-top:14px">${panel('Tarefas em aberto', 'Follow-ups e atividades com prazo', tasks.length ? `<div>${tasks.map(t => `<div class="task ${t.overdue ? 'overdue' : ''}"><div class="main"><strong>${esc(t.title)}</strong><small>${t.company_id ? `<a class="src" href="#/empresa/${t.company_id}">${esc(t.company_name)}</a> · ` : ''}${t.due_at ? (t.overdue ? 'atrasada desde ' : 'até ') + when(t.due_at) : 'sem prazo'}</small></div><button class="small" onclick="doneTask(${t.id})">✓ Concluir</button></div>`).join('')}</div>` : '<p class="empty">Nenhuma tarefa em aberto.</p>')}
      ${panel('Regras do funil', '', `<p class="note">• “Perdido” exige motivo.<br>• Empresas na lista de supressão (“Não contatar”) não podem receber contato nem mudar de etapa até serem retiradas da lista em Configurações.<br>• Um novo contato antes do intervalo mínimo (Configurações) pede confirmação, para evitar abordagens repetidas.<br>• Registrar contato, resposta, reunião, proposta ou contrato avança a etapa automaticamente; nunca a faz voltar.</p>`)}</div>`;
}
async function doneTask(id) {
  try { await send('/tasks/' + id, 'PATCH', { done: true }); toast('Tarefa concluída.'); route(); }
  catch (e) { toast(errMsg(e), 6000, true); }
}

// ------------------------------------------------------------------ ficha da empresa
const KINDS = [['contato', 'Contato realizado'], ['follow_up', 'Follow-up'], ['resposta', 'Resposta recebida'], ['reuniao', 'Reunião'],
  ['proposta', 'Proposta enviada'], ['contrato', 'Contrato fechado'], ['nota', 'Anotação']];
const CHANNELS = [['email', 'E-mail'], ['telefone', 'Telefone'], ['whatsapp', 'WhatsApp'], ['presencial', 'Presencial'], ['linkedin', 'LinkedIn'], ['outro', 'Outro']];
let SHEET = null;
async function viewEmpresa(id) {
  const c = SHEET = await api('/companies/' + encodeURIComponent(id));
  const sd = c.score_detail;
  const fact = (k, v) => v ? `<span><b>${k}:</b> ${esc(v)}</span>` : '';
  const comps = sd.components.map(p => `<div class="comp"><b>${esc(p.label)} <span class="nat ${natCls(p.nature)}">${esc(p.nature)}</span></b><span class="pts ${p.points < 0 ? 'neg' : ''}">${p.points > 0 ? '+' : ''}${p.points}</span><small>${esc(p.reason)}</small></div>`).join('');
  const signals = c.signals_detail.length ? c.signals_detail.map(s => `<div class="signal"><div class="badges" style="margin:0 0 4px"><span class="tag ${esc(s.type)}">${esc(s.type_label)}</span><span class="nat ${natCls(s.nature)}">${esc(s.nature)}</span>${s.status === 'discarded' ? '<span class="badge bad">DESCARTADO</span>' : ''}<span class="badge">força ${s.strength}/30</span></div>
      <strong>${s.url ? `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</strong>
      <p>${esc(s.source)} · captado em ${when(s.captured_at)}${s.deadline ? ' · prazo ' + when(s.deadline) : ''}</p><p>Leitura: ${esc(s.reading)}</p>${s.excerpt ? `<p class="muted">${esc(s.excerpt)}</p>` : ''}<p class="muted">⚠ ${esc(s.caveat)}</p></div>`).join('')
    : '<p class="empty">Nenhum sinal captado para esta empresa. A pontuação vem do cadastro (fato), do porte e capital (indício) e do setor (hipótese).</p>';
  const timeline = c.timeline.length ? `<ul class="timeline">${c.timeline.map(t => `<li class="${esc(t.kind)}"><small>${when(t.at)} · ${esc(t.kind_label)}${t.channel ? ' · ' + esc(t.channel) : ''}${t.outcome ? ' · ' + esc(t.outcome) : ''}</small><p>${esc(t.summary)}</p></li>`).join('')}</ul>` : '<p class="empty">Sem histórico.</p>';
  const tasks = c.tasks.length ? c.tasks.map(t => `<div class="task ${!t.done && t.due_at && new Date(t.due_at) < new Date() ? 'overdue' : ''}"><div class="main"><strong>${t.done ? '✓ ' : ''}${esc(t.title)}</strong><small>${t.due_at ? 'até ' + when(t.due_at) : 'sem prazo'}${t.done ? ' · concluída' : ''}</small></div>${t.done ? '' : `<button class="small" onclick="doneTask(${t.id})">✓ Concluir</button>`}</div>`).join('') : '<p class="empty">Nenhuma tarefa.</p>';
  const mc = c.market_context;
  const market = mc ? `<p class="note">${esc(mc.aviso)}</p><div class="kpi">${fmt(mc.total_processos)}</div><p class="note">processos de cobrança na Justiça Estadual de ${esc(mc.uf)} (${esc(mc.periodo?.inicio || '')} a ${esc(mc.periodo?.fim || '')})</p>${(mc.tipos || []).map(t => `<div class="bar"><span>${esc(t.label)}</span><b>${fmt(t.processos)}</b></div>`).join('')}`
    : '<p class="empty">Sem fotografia do DataJud para a UF desta empresa. Gere em “Radar de mercado”.</p>';
  const suppressed = c.suppressed || c.stage === 'nao_contatar';
  V().innerHTML = `<p style="margin:0 0 10px"><a class="src" href="#/crm">← CRM comercial</a> · <a class="src" href="#/empresas">Encontrar empresas</a></p>
    <div class="sheethead"><div><small class="eyebrow">Ficha da empresa · ${esc(c.registry_source || 'origem não informada')}</small><h1>${esc(c.name)}</h1>
      <div class="facts-line">${fact('CNPJ', c.cnpj_formatted)}${fact('Fantasia', c.trade_name)}${fact('Local', loc(c))}${fact('Região', c.region)}${fact('Situação', c.registration_status)}</div>
      <div class="facts-line">${fact('CNAE', [c.cnae_main, c.cnae_desc].filter(Boolean).join(' — '))}${fact('Perfil', c.profile_label)}${fact('Porte', c.company_size)}${fact('Capital social', money(c.capital_social))}${fact('Abertura', c.opened_at ? c.opened_at.split('-').reverse().join('/') + (c.years_active != null ? ` (${c.years_active.toLocaleString('pt-BR')} anos)` : '') : '')}${fact('Natureza jurídica', c.legal_nature)}</div>
      ${c.debt_types.length ? `<div class="facts-line"><span><b>Inadimplência típica do setor:</b> ${esc(c.debt_types.join(' · '))} <span class="nat hipotese">hipótese</span></span></div>` : ''}</div>
      <div class="bigscore">${pill(c.score, c.band, c.band_label)}<small>${esc(c.band_label)} · etapa: ${esc(c.stage_label)}</small><small>${esc(sd.disclaimer)}</small></div></div>
    ${c.blocked_reason ? `<div class="blocked">⛔ ${esc(c.blocked_reason)} Contatos e mudanças de etapa ficam bloqueados.</div>` : ''}
    ${c.pending_note ? `<div class="warnbox" style="margin:0 0 14px">${esc(c.pending_note)}</div>` : ''}
    <div class="sheet"><div class="stack">
      ${panel('Etapa e próxima atividade', '', `<form id="f-stage" class="form">
        <label class="f">Etapa<select name="stage" ${suppressed ? 'disabled' : ''}>${opts(STAGE_OPTS, c.stage)}</select></label>
        <label class="f">Motivo da mudança (opcional)<input name="stage_reason" maxlength="500"></label>
        <label class="f full" id="lost-box" style="${c.stage === 'perdido' ? '' : 'display:none'}">Motivo da perda (obrigatório para “Perdido”)<textarea name="lost_reason" maxlength="1000">${esc(c.lost_reason || '')}</textarea></label>
        <label class="f">Próxima atividade<input name="next_action" maxlength="500" value="${esc(c.next_action || '')}" placeholder="Ex.: ligar para o financeiro"></label>
        <label class="f">Quando<input name="next_action_at" type="datetime-local" value="${toLocalInput(c.next_action_at)}"></label>
        <label class="f">Valor potencial (R$, informado por você)<input name="potential_value" type="number" min="0" step="0.01" value="${c.potential_value ?? ''}"></label>
        <label class="f">Site institucional<input name="website" maxlength="500" value="${esc(c.website || '')}"></label>
        <label class="f">E-mail institucional<input name="institutional_email" type="email" maxlength="255" value="${esc(c.institutional_email || '')}"></label>
        <label class="f full">Anotações<textarea name="notes" maxlength="5000">${esc(c.notes || '')}</textarea></label>
        <div class="end"><button class="primary">Salvar</button></div></form>`)}
      ${panel('Registrar interação', c.last_outreach_at ? 'Último contato em ' + when(c.last_outreach_at) : 'Nenhum contato registrado', `<form id="f-int" class="form">
        <label class="f">Tipo<select name="kind">${opts(KINDS, 'contato')}</select></label>
        <label class="f">Canal<select name="channel">${opts(CHANNELS, 'email', '—')}</select></label>
        <label class="f full">O que aconteceu<textarea name="summary" required minlength="2" maxlength="5000" placeholder="Ex.: e-mail enviado ao financeiro apresentando o serviço"></textarea></label>
        <label class="f">Quando (vazio = agora)<input name="happened_at" type="datetime-local"></label>
        <label class="f">Criar follow-up em (dias)<input name="follow_up_days" type="number" min="1" max="90" placeholder="opcional"></label>
        <div id="int-warn" class="full"></div>
        <div class="end"><button class="primary" ${suppressed ? 'disabled title="Empresa na lista de supressão"' : ''}>Registrar</button></div></form>`)}
      ${panel('Tarefas', '', `${tasks}<form id="f-task" class="form" style="margin-top:10px"><label class="f">Nova tarefa<input name="title" required minlength="2" maxlength="250" placeholder="Ex.: enviar proposta"></label><label class="f">Prazo<input name="due_at" type="datetime-local"></label><div class="end"><button>＋ Adicionar tarefa</button></div></form>`)}
      ${panel('Não contatar (opt-out)', '', suppressed
        ? `<p class="note">Esta empresa está na lista de supressão. Para voltar a trabalhá-la, retire-a da lista em <a class="src" href="#/config">Configurações</a> (ela volta como “Acompanhar futuramente”).</p>`
        : `<form id="f-sup" class="form"><label class="f full">Motivo (ex.: pediu para não receber contato)<input name="reason" maxlength="1000"></label><div class="end"><button>⛔ Incluir na lista de supressão</button></div></form>`)}
    </div><div class="stack">
      ${panel('Por que esta pontuação', `Total ${c.score}/100 · ${esc(c.band_label)}`, comps)}
      ${panel('Sinais e evidências', 'Origem de cada informação', signals)}
      ${panel('Histórico', 'Contatos, respostas, mudanças de etapa e registros do sistema', timeline)}
      ${panel('Contexto regional (DataJud)', '', market)}
    </div></div>`;
  bindSheet(c);
}
function bindSheet(c) {
  const fs = $('f-stage');
  fs.stage.addEventListener('change', () => { $('lost-box').style.display = fs.stage.value === 'perdido' ? '' : 'none'; });
  fs.addEventListener('submit', async e => {
    e.preventDefault();
    const body = {}, f = fs;
    if (!f.stage.disabled && f.stage.value !== c.stage) { body.stage = f.stage.value; if (f.stage_reason.value.trim()) body.stage_reason = f.stage_reason.value.trim(); }
    if (f.stage.value === 'perdido' && f.lost_reason.value.trim() !== (c.lost_reason || '')) body.lost_reason = f.lost_reason.value.trim();
    const txt = k => { const v = f[k].value.trim(); if (v !== (c[k] || '')) body[k] = v || null; };
    ['next_action', 'website', 'institutional_email', 'notes'].forEach(txt);
    const at = fromLocalInput(f.next_action_at.value);
    if (toLocalInput(at) !== toLocalInput(c.next_action_at)) body.next_action_at = at;
    const pv = f.potential_value.value === '' ? null : Number(f.potential_value.value);
    if (pv !== (c.potential_value ?? null)) body.potential_value = pv;
    if (!Object.keys(body).length) return toast('Nada mudou.');
    try { await send('/companies/' + c.id, 'PATCH', body); toast('Ficha atualizada.'); viewEmpresa(c.id); }
    catch (err) { toast(errMsg(err), 8000, true); }
  });
  const fi = $('f-int');
  const sendInt = async (confirmRepeat) => {
    const body = { kind: fi.kind.value, summary: fi.summary.value.trim(), confirm_repeat: !!confirmRepeat };
    if (fi.channel.value) body.channel = fi.channel.value;
    if (fi.happened_at.value) body.happened_at = fromLocalInput(fi.happened_at.value);
    if (fi.follow_up_days.value) body.follow_up_days = Number(fi.follow_up_days.value);
    try {
      const r = await send(`/companies/${c.id}/interactions`, 'POST', body);
      toast(`Registrado. Etapa: ${r.stage_label}.`); viewEmpresa(c.id);
    } catch (err) {
      const m = errMsg(err);
      if (err.status === 409 && /Confirme/.test(m)) {
        $('int-warn').innerHTML = `<div class="warnbox">${esc(m)} <button type="button" class="small" id="int-confirm">Registrar mesmo assim</button></div>`;
        $('int-confirm').onclick = () => sendInt(true);
      } else toast(m, 8000, true);
    }
  };
  fi.addEventListener('submit', e => { e.preventDefault(); sendInt(false); });
  $('f-task').addEventListener('submit', async e => {
    e.preventDefault();
    const t = e.target, body = { title: t.title.value.trim() };
    if (t.due_at.value) body.due_at = fromLocalInput(t.due_at.value);
    try { await send(`/companies/${c.id}/tasks`, 'POST', body); toast('Tarefa criada.'); viewEmpresa(c.id); }
    catch (err) { toast(errMsg(err), 7000, true); }
  });
  const sup = $('f-sup');
  if (sup) sup.addEventListener('submit', async e => {
    e.preventDefault();
    try { await send('/suppression', 'POST', { company_id: c.id, reason: sup.reason.value.trim() }); toast('Empresa incluída na lista de supressão.'); viewEmpresa(c.id); }
    catch (err) { toast(errMsg(err), 7000, true); }
  });
}

// ------------------------------------------------------------------ radar de mercado (DataJud)
function bars(items, labelKey, extra) {
  const max = Math.max(1, ...items.map(x => x.processos));
  return items.map(x => `<div class="bar"><span>${esc(x[labelKey] || x.codigo_ibge || '—')}</span><b>${fmt(x.processos)}</b><i style="--w:${(100 * x.processos / max).toFixed(1)}%"></i>${extra ? `<small>${esc(extra(x))}</small>` : ''}</div>`).join('');
}
async function viewRadar() {
  V().innerHTML = head('DataJud · CNJ', 'Radar de mercado', 'Volume e tipo de cobrança ajuizada na Justiça Estadual por UF. Dado agregado: orienta onde e em quais setores prospectar, mas não diz nada sobre uma empresa específica.',
    '<select id="m-uf" onchange="loadMarket()" style="width:auto"></select><button class="capture" id="m-refresh" onclick="refreshMarket()">⟳ Atualizar pelo DataJud</button>')
    + '<div id="m-body" class="market"><p class="note">Carregando…</p></div>';
  $('m-uf').innerHTML = UFS.map(u => `<option ${u === 'AM' ? 'selected' : ''}>${u}</option>`).join('');
  loadMarket();
}
function renderMarket(d) {
  $('m-body').innerHTML = `<article class="panel"><small class="eyebrow">Tipos de inadimplência · ${esc(d.tribunal)} · ${esc(d.periodo.inicio)} a ${esc(d.periodo.fim)}</small>
      <div class="kpi">${fmt(d.total_processos)}</div><p class="note">processos de cobrança ajuizados no período</p>
      ${bars(d.tipos_de_inadimplencia, 'label', x => 'assuntos: ' + x.assuntos.join(', '))}
      <p class="note">Não classificados (genéricos): ${esc(d.assuntos_nao_classificados.slice(0, 6).map(a => `${a.nome} (${fmt(a.processos)})`).join(' · '))}</p></article>
    <article class="panel"><small class="eyebrow">Classes</small>${bars(d.classes, 'nome')}<small class="eyebrow" style="display:block;margin-top:14px">Municípios</small>${bars(d.municipios.slice(0, 10), 'nome')}
      <p class="note">${esc(d.limites.join(' '))}<br>Fotografia de ${when(d.created_at)}.</p></article>`;
}
async function loadMarket() {
  const uf = $('m-uf').value;
  try { renderMarket(await api('/market/datajud?uf=' + uf)); }
  catch (e) { $('m-body').innerHTML = `<p class="note">${esc(errMsg(e, `Sem dados de ${uf} ainda.`))} Clique em “Atualizar pelo DataJud” (10 s a 2 min).</p>`; }
}
async function refreshMarket() {
  const btn = $('m-refresh'), uf = $('m-uf').value;
  btn.disabled = true; btn.textContent = 'Consultando DataJud…';
  try { renderMarket(await api('/market/datajud?uf=' + uf, { method: 'POST' })); toast(`Mapa de ${uf} atualizado.`); }
  catch (e) { toast(errMsg(e, 'O DataJud não respondeu (o CNJ limita a fila de buscas). Tente em instantes.'), 8000, true); }
  finally { btn.disabled = false; btn.textContent = '⟳ Atualizar pelo DataJud'; }
}

// ------------------------------------------------------------------ fontes
const ST_CLS = { 'Integrada e testada': 'integrada', 'Com erro de coleta': 'erro', 'Consultada': 'consultada', 'Indisponível': 'indisponivel', 'Planejada': 'planejada' };
async function viewFontes() {
  const [d, runs] = await Promise.all([api('/sources'), api('/capture/runs').catch(() => [])]);
  const group = (cat, title) => {
    const items = d.sources.filter(s => s.category === cat);
    return panel(`${title} (${items.length})`, esc(d.legend[cat] || ''), items.map(s => {
      const url = s.url ? (s.url.includes('{') ? s.url.split('{')[0] : s.url) : null;
      const ds = s.display_status || { integrada: 'Integrada e testada', consultada: 'Consultada', planejada: 'Planejada' }[cat];
      return `<div class="source"><b>${esc(s.name.slice(0, 2).toUpperCase())}</b><span><strong>${url ? `<a class="src" href="${esc(url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}</strong><small>${esc(s.use || '')}</small><small>${esc(s.status)}</small>${s.last_error ? `<small style="color:var(--bad)">Última falha: ${esc(s.last_error)}</small>` : ''}</span><i class="st ${ST_CLS[ds] || ''}">${esc(ds)}</i></div>`;
    }).join(''));
  };
  V().innerHTML = head('Proveniência', 'Fontes de dados', `Verificado em ${esc(d.verified_at)}. Só aparece como “Integrada e testada” o conector testado com dados reais; “Com erro de coleta” indica que a última captação daquela fonte falhou.`)
    + `<div class="stack">${group('integrada', 'Integradas')}${group('consultada', 'Consultadas')}${group('planejada', 'Planejadas (não conectadas)')}
    ${panel('Últimas captações', '', runs.length ? `<div class="tablebox"><table><thead><tr><th>Fonte</th><th>Início</th><th>Status</th><th>Lidos</th><th>Novos</th><th>Mensagem</th></tr></thead><tbody>${runs.slice(0, 15).map(r => `<tr><td>${esc(r.source_name)}</td><td>${when(r.started_at)}</td><td><span class="badge ${r.status === 'completed' ? 'ok' : r.status === 'failed' ? 'bad' : 'warn'}">${esc(r.status)}</span></td><td>${fmt(r.records_seen)}</td><td>${fmt(r.records_created)}</td><td><small>${esc(r.message)}</small></td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">Nenhuma captação registrada.</p>')}</div>`;
}

// ------------------------------------------------------------------ configurações, supressão e LGPD
async function viewConfig() {
  const [s, sup] = await Promise.all([api('/settings'), api('/suppression')]);
  V().innerHTML = head('Preferências e conformidade', 'Configurações', 'Ajustes usados pela pontuação, pela inteligência do dia e pela trava contra abordagens repetidas.')
    + `<div class="grid2">${panel('Atuação comercial', '', `<form id="f-set" class="form">
        <div class="full"><p class="note" style="margin:0 0 6px">UFs de atuação (nenhuma marcada = Brasil inteiro). Empresas fora delas perdem os pontos de geografia.</p><div class="ufs">${UFS.map(u => `<label><input type="checkbox" name="uf" value="${u}" ${s.ufs_atuacao.includes(u) ? 'checked' : ''}>${u}</label>`).join('')}</div></div>
        <label class="f">Dias mínimos entre contatos<input name="dias" type="number" min="1" max="90" value="${s.dias_entre_contatos}"></label>
        <label class="f">Serviço oferecido<input name="servico" maxlength="200" value="${esc(s.servico || '')}"></label>
        <div class="end"><button class="primary">Salvar configurações</button></div></form>`)}
      ${panel('Lista de supressão (não contatar)', 'Empresas que pediram para não receber contato ou que você bloqueou', `${sup.length ? `<div>${sup.map(x => `<div class="task"><div class="main"><strong>${x.company_id ? `<a class="src" href="#/empresa/${x.company_id}">${esc(x.company_name || x.cnpj)}</a>` : esc(x.company_name || x.cnpj || '—')}</strong><small>${esc(x.cnpj || '')}${x.reason ? ' · ' + esc(x.reason) : ''} · desde ${day(x.created_at)}</small></div><button class="small" onclick="unsuppress(${x.id})">Retirar</button></div>`).join('')}</div>` : '<p class="empty">Lista vazia.</p>'}
        <form id="f-addsup" class="form" style="margin-top:10px"><label class="f">CNPJ<input name="cnpj" required placeholder="00.000.000/0000-00"></label><label class="f">Motivo<input name="reason" maxlength="1000"></label><div class="end"><button>⛔ Incluir</button></div></form>`)}
      ${panel('Dados e LGPD', '', `<p class="note">• A base guarda só dados de pessoa jurídica: razão social, CNAE, porte, capital, município/UF e situação cadastral. Sócios, CPF, e-mail e telefone do cadastro da Receita são descartados na importação; empresário individual (natureza 2135) fica fora por padrão.<br>• Dados judiciais (DataJud) são agregados por UF e não identificam empresas.<br>• Nenhum contato é enviado pelo sistema: abordagens, cobranças, protestos e negativações dependem sempre de decisão humana.<br>• Toda mudança de etapa, supressão, exportação e alteração de configurações fica na trilha de auditoria.</p>
        <div class="actions"><button onclick="exportCSV()">⇩ Exportar empresas (CSV, só PJ, sem suprimidas)</button></div>`)}</div>`;
  $('f-set').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target, ufs = [...f.querySelectorAll('input[name=uf]:checked')].map(i => i.value);
    try { await send('/settings', 'PUT', { ufs_atuacao: ufs, dias_entre_contatos: Number(f.dias.value), servico: f.servico.value.trim() }); toast('Configurações salvas.'); viewConfig(); }
    catch (err) { toast(errMsg(err), 7000, true); }
  });
  $('f-addsup').addEventListener('submit', async e => {
    e.preventDefault();
    try { await send('/suppression', 'POST', { cnpj: e.target.cnpj.value, reason: e.target.reason.value.trim() }); toast('Incluída na lista de supressão.'); viewConfig(); }
    catch (err) { toast(errMsg(err), 7000, true); }
  });
}
async function unsuppress(id) {
  try { await send('/suppression/' + id, 'DELETE'); toast('Retirada da lista. A empresa volta como “Acompanhar futuramente”.'); route(); }
  catch (e) { toast(errMsg(e), 7000, true); }
}

route();
