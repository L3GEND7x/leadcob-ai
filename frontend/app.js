let data = [];
const $ = id => document.getElementById(id);

async function api(path, opt = {}) {
  const r = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...opt });
  if (!r.ok) throw Error(await r.text());
  return r.json();
}

function esc(x) {
  return String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

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
const money = v => v ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : '';
const when = iso => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); };

async function load() {
  try {
    const status = $('status').value;
    const [s, rows] = await Promise.all([api('/dashboard/summary'), api('/opportunities' + (status ? `?status=${status}` : ''))]);
    data = rows;
    $('total').textContent = s.total; $('hiring').textContent = s.hiring; $('outsourcing').textContent = s.outsourcing;
    $('procurements').textContent = s.public_procurement || 0; $('proven').textContent = s.proven || 0;
    $('toconfirm').textContent = s.to_confirm || 0; $('prospects-count').textContent = s.prospects || 0; $('qualified').textContent = s.qualified; $('average').textContent = s.average_score;
    render(); lastRun();
  } catch (e) {
    $('rows').innerHTML = '<tr><td colspan="7">Falha ao carregar a API.</td></tr>'; console.error(e);
  }
}

function render() {
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
    return `<tr><td><strong>${esc(x.company_name)}</strong><small>${esc(x.title)}</small>${badges}${why}</td>
      <td><span class="tag ${x.kind}">${KIND[x.kind] || esc(x.kind)}</span></td>
      <td>${esc([x.city, x.state].filter(Boolean).join(' / ') || '—')}</td>
      <td>${src}${extra ? `<span class="deadline">${extra}</span>` : ''}${dl}</td>
      <td><span class="score" title="${esc(x.score_reason)}">${x.score}/100</span></td>
      <td><span class="status ${x.status}">${STATUS[x.status] || 'EM ANÁLISE'}</span></td>
      <td><button class="action" title="Executar agentes" onclick="runAgents(${x.id})">↗</button></td></tr>`;
  }).join('') : '<tr><td colspan="7">Nenhuma oportunidade encontrada.</td></tr>';
}

async function runAgents(id) {
  try {
    const r = await api(`/agents/run/${id}`, { method: 'POST' });
    const issues = r.agents.audit.issues.length ? ` · ${r.agents.audit.issues.length} alerta(s) de auditoria` : '';
    toast(`Agentes concluídos · score ${r.opportunity.score}/100${issues}`); load();
  } catch (e) { toast('Falha ao executar agentes.'); }
}

function toast(t, ms = 3500) {
  $('toast').textContent = t; $('toast').style.display = 'block';
  clearTimeout(toast._t); toast._t = setTimeout(() => $('toast').style.display = 'none', ms);
}

async function lastRun() {
  try {
    const runs = await api('/capture/runs');
    if (!runs.length) { $('lastrun').textContent = 'Nenhuma captação executada ainda.'; return; }
    const r = runs[0];
    $('lastrun').textContent = `Última captação (${when(r.started_at)}): ${r.status} — ${r.message}`;
  } catch (e) { /* painel continua funcional */ }
}

async function capturePNCP() {
  const btn = $('capture-pncp');
  btn.disabled = true; btn.textContent = 'Consultando PNCP… (pode levar 1–3 min)';
  try {
    const r = await api('/capture/pncp?mode=busca&max_pages=2', { method: 'POST' });
    const partial = r.status === 'partial' ? ` · ${r.errors.length} consulta(s) falharam — repita mais tarde` : '';
    toast(`PNCP: ${r.found} encontrados · ${r.discarded} descartados por aderência · ${r.proven} comprovadas · ${r.to_confirm} sinais a confirmar · ${r.created} novos${partial}`, 9000);
    await load();
  } catch (e) {
    toast('O PNCP não respondeu (a API limita rajadas de consultas). Tente novamente em alguns minutos.', 7000); console.error(e); lastRun();
  } finally { btn.disabled = false; btn.textContent = '⌕ Buscar editais PNCP'; }
}

$('newform').addEventListener('submit', async e => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target).entries());
  try {
    await api('/opportunities', { method: 'POST', body: JSON.stringify(d) });
    document.querySelector('dialog').close(); e.target.reset(); toast('Oportunidade cadastrada.'); load();
  } catch (err) { toast('Não foi possível salvar; revise os campos.'); }
});
async function captureJobs() {
  const btn = $('capture-jobs');
  btn.disabled = true; btn.textContent = 'Consultando boards…';
  try {
    const r = await api('/capture/jobs', { method: 'POST' });
    toast(`Vagas: ${r.jobs_read} lidas em ${r.boards_fetched} boards · ${r.matches} aderentes · ${r.created} novas · ${r.closed} encerradas · ${r.competitors} de concorrentes${r.errors.length ? ` · ${r.errors.length} board(s) com falha` : ''}`, 9000);
    await load();
  } catch (e) {
    let msg = 'Falha ao consultar vagas.'; try { msg = JSON.parse(e.message).detail || msg } catch (_) {}
    toast(msg, 7000);
  } finally { btn.disabled = false; btn.textContent = '↗ Buscar vagas públicas'; }
}

let prospectTimer;
function loadProspects() { clearTimeout(prospectTimer); prospectTimer = setTimeout(renderProspects, 250); }
async function renderProspects() {
  const p = new URLSearchParams();
  [['q', 'p-search'], ['segment', 'p-segment'], ['uf', 'p-uf'], ['size', 'p-size']].forEach(([k, id]) => { const v = $(id).value.trim(); if (v) p.set(k, v); });
  try {
    const rows = await api('/prospects?' + p.toString());
    $('p-rows').innerHTML = rows.length ? rows.map(c => `<tr>
      <td><strong>${esc(c.name)}</strong><small>${esc(c.cnpj_formatted || '')}${c.trade_name ? ' · ' + esc(c.trade_name) : ''}</small>${c.opportunities ? `<div class="badges"><span class="badge ok">${c.opportunities} SINAL(IS) VINCULADO(S)</span></div>` : ''}</td>
      <td>${esc(c.cnae_main || '—')}<small>${esc(c.cnae_desc || '')}</small></td>
      <td>${esc(c.target_profile_label || c.target_profile || '—')}</td>
      <td>${esc([c.city, c.state].filter(Boolean).join(' / ') || '—')}</td>
      <td>${esc(c.company_size || '—')}<small>${c.capital_social ? money(c.capital_social) : ''}</small></td>
      <td><small>${esc(c.registry_source || '')}</small></td>
      <td>${c.cnpj ? `<button class="action" title="Atualizar pelo CNPJ" onclick="enrich(${c.id})">⟳</button>` : ''}</td></tr>`).join('')
      : '<tr><td colspan="7">Nenhuma empresa-alvo. Rode o importador de CNPJ (job em lote) ou consulte um CNPJ no cadastro.</td></tr>';
  } catch (e) { $('p-rows').innerHTML = '<tr><td colspan="7">Falha ao carregar empresas-alvo.</td></tr>'; }
}

async function enrich(id) {
  try { await api(`/companies/${id}/enrich`, { method: 'POST' }); toast('Cadastro atualizado pela base pública do CNPJ.'); renderProspects(); }
  catch (e) { let m = 'Falha na consulta do CNPJ.'; try { m = JSON.parse(e.message).detail || m } catch (_) {} toast(m); }
}

async function fillFromCNPJ() {
  const f = $('newform'), v = $('form-cnpj').value;
  try {
    const d = await api('/cnpj/' + encodeURIComponent(v.replace(/[^0-9A-Za-z]/g, '')));
    f.company_name.value = d.razao_social || f.company_name.value;
    f.segment.value = d.cnae_descricao || f.segment.value;
    f.city.value = d.municipio || f.city.value; f.state.value = d.uf || f.state.value;
    toast(`${d.razao_social} · ${d.situacao_cadastral} · fonte: ${d.source}`);
  } catch (e) { let m = 'CNPJ não localizado.'; try { m = JSON.parse(e.message).detail || m } catch (_) {} toast(m); }
}

async function loadSources() {
  try {
    const d = await api('/sources');
    const label = { integrada: ['INTEGRADAS', 'connected', 'INTEGRADA'], consultada: ['CONSULTADAS', 'ref', 'REFERÊNCIA'], planejada: ['PLANEJADAS', 'planned', 'PLANEJADA'] };
    $('sources-list').innerHTML = ['integrada', 'consultada', 'planejada'].map(cat => {
      const items = d.sources.filter(s => s.category === cat);
      return `<div class="srcgroup">${label[cat][0]} (${items.length})</div>` + items.map(s => `<div class="source"><b>${esc(s.name.slice(0, 2).toUpperCase())}</b><span><strong>${s.url ? `<a class="src" href="${esc(s.url.includes('{') ? s.url.split('{')[0] : s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}</strong><small>${esc(s.status)}</small></span><i class="${label[cat][1]}">${label[cat][2]}</i></div>`).join('');
    }).join('') + `<p class="note">Verificado em ${esc(d.verified_at)} · boards de vagas configurados: ${d.job_boards_configured ?? '—'}</p>`;
  } catch (e) { $('sources-list').innerHTML = '<p class="note">Falha ao carregar o catálogo.</p>'; }
}

async function loadSegments() {
  try { const segs = await api('/segments'); $('p-segment').innerHTML += segs.map(s => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join(''); } catch (e) {}
}

$('status').addEventListener('change', load);
load(); loadSegments(); renderProspects(); loadSources();
