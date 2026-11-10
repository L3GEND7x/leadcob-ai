/* LeadCob — camada da página publicada (claude.ai).
 *
 * Substitui a função api() do frontend. Lê os dados embutidos (window.__DEMO, gerados pela API real
 * em scripts/build_dashboard_snapshot.py) e usa os recursos da página publicada:
 *  - db: guarda as ações do CRM (coleção crm_eventos), resultados dos agentes, oportunidades
 *        cadastradas à mão, UFs pedidas para o DataJud e o horário do último pedido de busca;
 *  - mcp (conector "Claude Code Remote", ferramenta fire_trigger): dispara a tarefa agendada
 *        que busca os dados ao vivo e republica a página.
 * Cada ação do CRM vale na hora nesta tela; a tarefa de hora em hora reaplica todas as ações no
 * banco do sistema e recalcula pontuação, central de comando e inteligência do dia.
 * Sem esses recursos (arquivo aberto fora do claude.ai), a página continua legível.
 */
const LC = (() => {
  const D = window.__DEMO, META = D.__meta || {};
  const S = { db: null, mcp: null, agents: {}, manual: [], ufs: [], crm: [], crmLoaded: false };
  const APPLIED = new Set(META.crm_aplicados || []), MANUAL_DONE = new Set(META.manuais_aplicados || []);
  const fail = (detail, status) => { const e = Error(JSON.stringify({ detail })); e.status = status; throw e; };
  const hhmm = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  const ddmm = (iso) => new Date(iso).toLocaleDateString('pt-BR');
  const keyOf = (o) => (o.source_key || ('manual:' + o._doc)).replace(/[^A-Za-z0-9_.~:@+-]/g, '_').slice(0, 190);
  const clone = (x) => JSON.parse(JSON.stringify(x));

  // --- agentes (mesma lógica de backend/app/agents e services/scoring.py) ---
  function scoreOpportunity(kind, description, evidence, url) {
    const text = `${description || ''} ${evidence || ''}`.toLowerCase();
    let score = 0; const why = [];
    if ((evidence || '').trim()) { score += 25; why.push('evidência textual registrada +25'); }
    if (url) { score += 10; why.push('URL de origem informada +10'); }
    const terms = ['cobrança', 'inadimpl', 'recuperação de crédito', 'contas a receber', 'negociação', 'carteira vencida', 'crédito', 'financeiro'];
    const found = terms.filter(t => text.includes(t));
    if (found.length) { const pts = Math.min(30, 10 + 5 * (found.length - 1)); score += pts; why.push(`sinais: ${found.join(', ')} +${pts}`); }
    const pts = kind === 'hiring' ? 10 : 15; score += pts; why.push(`frente ${kind} +${pts}`);
    if (['urgente', 'imediata', 'grande volume', 'alto volume'].some(t => text.includes(t))) { score += 10; why.push('sinal de urgência/volume +10'); }
    return [Math.min(score, 100), why.join('; ')];
  }
  function runPipeline(o) {
    const research = { source_present: !!o.source_name, url_present: !!o.source_url, evidence_present: !!(o.evidence || '').trim(),
      note: 'Proveniência registrada pelo coletor ou pelo cadastro manual.' };
    let qualification;
    if (o.commercial_signal && o.evidence_level) {   // captado por coletor: mantém a pontuação do classificador
      qualification = { score: o.score, reason: o.score_reason, recommended_status: o.commercial_signal === 'oportunidade_comprovada' ? 'qualified' : 'review' };
    } else {
      const [score, reason] = scoreOpportunity(o.kind, o.description, o.evidence, o.source_url);
      qualification = { score, reason, recommended_status: score >= 55 ? 'qualified' : 'review' };
    }
    const issues = [];
    if (!research.evidence_present) issues.push('Sem evidência textual.');
    if (!research.url_present) issues.push('Sem URL de origem; validar manualmente.');
    if (o.kind === 'outsourcing') issues.push('Terceirização é hipótese até confirmação direta da empresa.');
    if (o.kind === 'public_procurement') {
      if (o.evidence_level !== 'confirmada_api_oficial') issues.push('Registro só localizado no índice de busca; confirmar na API oficial ou no edital.');
      if (o.relevance === 'revisar') issues.push(`Aderência duvidosa: ${o.relevance_reason}`);
      if (o.opportunity_class !== 'edital_aberto') issues.push('Não há prazo de propostas aberto: tratar como sinal de mercado.');
      issues.push('Ler o edital: habilitação, qualificação técnica, forma de remuneração e prazo.');
    }
    if (o.kind === 'hiring' && o.evidence_level) issues.push('Vaga indica contratação interna; confirmar interesse em terceirizar no contato.');
    const audit = { passed: research.evidence_present && qualification.score >= 35, issues, human_review_required: true };
    return { research, qualification, audit };
  }

  // --- oportunidades: coleta embutida + cadastradas nesta página (até a próxima atualização incorporá-las) ---
  function allOpps() {
    const base = D['/opportunities'].map(o => ({ ...o }));
    S.manual.filter(m => !MANUAL_DONE.has(m._doc)).forEach((m, i) => base.push({ ...m, id: 900000 + i, company_id: null }));
    for (const o of base) {
      const a = S.agents[keyOf(o)];
      if (a) { o.status = a.status; o.score = a.score; o.score_reason = a.score_reason; o.agents_at = a.at; o.audit_issues = a.issues; }
    }
    return base.sort((x, y) => y.score - x.score);
  }
  function summary() {
    const ops = allOpps(), s = { ...D['/dashboard/summary'] };
    const n = (f) => ops.filter(f).length;
    Object.assign(s, {
      total: ops.length, hiring: n(o => o.kind === 'hiring'), outsourcing: n(o => o.kind === 'outsourcing'),
      public_procurement: n(o => o.kind === 'public_procurement'), qualified: n(o => o.status === 'qualified'),
      proven: n(o => o.commercial_signal === 'oportunidade_comprovada'),
      to_confirm: n(o => o.kind === 'public_procurement' && o.commercial_signal === 'sinal_a_confirmar'),
      average_score: ops.length ? Math.round(10 * ops.reduce((t, o) => t + o.score, 0) / ops.length) / 10 : 0,
    });
    return s;
  }

  // --- CRM: estado = dados embutidos + ações ainda não reaplicadas pela atualização horária ---
  const STAGES = ((D['/pipeline'] || {}).stages || []).map(s => [s.key, s.label]);
  const STAGE_LABEL = Object.fromEntries(STAGES), ORDER = Object.fromEntries(STAGES.map(([k], i) => [k, i]));
  const KIND_TO_STAGE = { contato: 'primeiro_contato', follow_up: 'aguardando_resposta', resposta: 'em_negociacao',
    reuniao: 'reuniao_agendada', proposta: 'proposta_enviada', contrato: 'cliente_conquistado' };
  const KIND_LABEL = { contato: 'Contato realizado', resposta: 'Resposta recebida', reuniao: 'Reunião', proposta: 'Proposta enviada',
    contrato: 'Contrato fechado', nota: 'Anotação', follow_up: 'Follow-up', etapa: 'Mudança de etapa', sistema: 'Registro do sistema' };
  const OUTREACH = new Set(['contato', 'follow_up', 'proposta']);
  const CHANNELS = new Set(['email', 'telefone', 'whatsapp', 'presencial', 'linkedin', 'outro']);
  const UFS = new Set(Object.values(D['/regions'] || {}).flat());
  const coKey = (c) => c.cnpj || ('nome:' + c.name);
  const pending = () => S.crm.filter(e => !APPLIED.has(e.id));
  const brl = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

  function makeFicha(s) {
    return { ...clone(s), legal_nature: null, cnae_secondary: [], notes: null, created_at: null, last_outreach_at: null, market_context: null,
      score_detail: { score: s.score, band: s.band, band_label: s.band_label, components: [], disclaimer: 'Ordem de prioridade comercial, não probabilidade de contratação ou de inadimplência.' },
      signals_detail: [], timeline: [], tasks: [], blocked_reason: s.suppressed ? 'Empresa na lista de supressão.' : null, stages: STAGES.map(([key, label]) => ({ key, label })) };
  }
  let VIEW = null, VIEW_SIG = null;
  function view() {
    const pend = pending(), sig = pend.map(e => e.id).join(',');
    if (VIEW && sig === VIEW_SIG) return VIEW;
    const V = { fichas: clone(D.fichas || {}), comps: clone(D.companies_all || []), settings: { ...(D['/settings'] || {}) },
      sup: clone(D['/suppression'] || []), byKey: {}, byId: {}, pend };
    V.comps.forEach(s => { V.byKey[coKey(s)] = s; V.byId[String(s.id)] = s; });
    for (const e of pend) { try { applyEvent(e, V); } catch (err) { console.warn('ação não aplicada', e, err); } }
    VIEW = V; VIEW_SIG = sig; return V;
  }
  function ficha(V, s) { return V.fichas[String(s.id)] || (V.fichas[String(s.id)] = makeFicha(s)); }
  function tl(f, kind, summary, at, channel) {
    f.timeline.unshift({ id: 'p', kind, kind_label: KIND_LABEL[kind] || kind, channel: channel || null, summary, outcome: null, at });
    f.timeline.sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }
  function setBoth(s, f, k, v) { s[k] = v; f[k] = v; }
  function setStage(s, f, st, why, at) {
    const old = f.stage; if (old === st) return;
    setBoth(s, f, 'stage', st); setBoth(s, f, 'stage_label', STAGE_LABEL[st]);
    tl(f, 'etapa', `${STAGE_LABEL[old] || old} → ${STAGE_LABEL[st]}` + (why ? ` (${why})` : ''), at);
  }
  function suppress(V, s, f, reason, at) {
    if (!V.sup.some(x => x.company_id === s.id || (s.cnpj && x.cnpj === s.cnpj)))
      V.sup.unshift({ id: 'p-' + at, cnpj: s.cnpj, company_id: s.id, company_name: s.name, reason: reason || '', created_at: at });
    setBoth(s, f, 'suppressed', true); setBoth(s, f, 'score', 0); setBoth(s, f, 'band', 'nao_contatar'); setBoth(s, f, 'band_label', 'Não contatar');
    f.blocked_reason = `Empresa na lista de supressão desde ${ddmm(at)}` + (reason ? `: ${reason}` : '.');
    if (f.stage !== 'nao_contatar') { setBoth(s, f, 'stage', 'nao_contatar'); setBoth(s, f, 'stage_label', STAGE_LABEL.nao_contatar); }
    tl(f, 'sistema', 'Incluída na lista de supressão' + (reason ? `: ${reason}` : ''), at);
  }
  function applyEvent(e, V) {
    const d = e.dados || {}, at = e.em;
    if (e.tipo === 'config') { Object.assign(V.settings, d); return; }
    if (e.tipo === 'empresa_criada') {
      if (V.byKey[e.chave]) return;
      const id = 'novo-' + e.id;
      const s = { id, name: d.name, trade_name: null, cnpj: d.cnpj || null, cnpj_formatted: d.cnpj ? d.cnpj.replace(/^(\w{2})(\w{3})(\w{3})(\w{4})(\d{2})$/, '$1.$2.$3/$4-$5') : null,
        cnae_main: d.cnae_main || null, cnae_desc: null, segment: d.segment || null, profile: null, profile_label: null, debt_types: [],
        city: d.city || null, state: d.state || null, region: null, company_size: null, capital_social: null, registration_status: null,
        opened_at: null, years_active: null, website: d.website || null, institutional_email: d.institutional_email || null,
        stage: 'identificada', stage_label: STAGE_LABEL.identificada, next_action: null, next_action_at: null, potential_value: null,
        lost_reason: null, score: 0, band: 'baixa', band_label: 'Pontuação calculada na próxima atualização', signals: 0,
        last_signal_at: null, suppressed: false, registry_source: 'Cadastro manual' };
      V.comps.push(s); V.byKey[e.chave] = s; V.byId[id] = s;
      const f = ficha(V, s); f.notes = d.notes || null; f.pending = 1;
      tl(f, 'sistema', 'Empresa cadastrada manualmente', at);
      return;
    }
    const s = V.byKey[e.chave];
    if (!s) {
      if (e.tipo === 'supressao') V.sup.unshift({ id: 'p-' + e.id, cnpj: d.cnpj || e.chave, company_id: null, company_name: null, reason: d.reason || '', created_at: at });
      if (e.tipo === 'supressao_removida') V.sup = V.sup.filter(x => x.cnpj !== (d.cnpj || e.chave));
      return;
    }
    const f = ficha(V, s);
    f.pending = (f.pending || 0) + 1;
    if (e.tipo === 'empresa_atualizada') {
      if ('lost_reason' in d) setBoth(s, f, 'lost_reason', d.lost_reason);
      if (d.stage) {
        if (d.stage === 'nao_contatar') suppress(V, s, f, d.stage_reason || "Marcada como 'Não contatar' no CRM", at);
        else setStage(s, f, d.stage, d.stage_reason || (d.stage === 'perdido' ? d.lost_reason || f.lost_reason : null), at);
      }
      ['next_action', 'next_action_at', 'potential_value', 'notes', 'website', 'institutional_email'].forEach(k => { if (k in d) setBoth(s, f, k, d[k]); });
      if ('potential_value' in d) tl(f, 'nota', d.potential_value != null ? `Potencial comercial informado: ${brl(d.potential_value)}` : 'Potencial comercial removido', at);
      if ('next_action' in d || 'next_action_at' in d)
        tl(f, 'nota', `Próxima atividade: ${f.next_action || '—'}` + (f.next_action_at ? ` em ${new Date(f.next_action_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}` : ''), at);
    } else if (e.tipo === 'interacao') {
      const when = d.happened_at || at;
      tl(f, d.kind, d.summary, when, d.channel);
      if (OUTREACH.has(d.kind) && (!f.last_outreach_at || when > f.last_outreach_at)) f.last_outreach_at = when;
      const target = KIND_TO_STAGE[d.kind];
      if (target && !['perdido', 'nao_contatar'].includes(f.stage) && !f.suppressed && ORDER[target] > (ORDER[f.stage] ?? 0))
        setStage(s, f, target, 'registro de ' + KIND_LABEL[d.kind].toLowerCase(), at);
      if (d.follow_up_days) f.tasks.push({ id: 'p-' + e.id, title: `Follow-up: ${s.name}`.slice(0, 250), kind: 'follow_up',
        due_at: new Date(Date.parse(when) + d.follow_up_days * 864e5).toISOString(), done: false });
    } else if (e.tipo === 'tarefa') {
      f.tasks.push({ id: 'p-' + e.id, title: d.title, kind: d.kind || 'follow_up', due_at: d.due_at || null, done: false });
    } else if (e.tipo === 'tarefa_concluida') {
      const t = f.tasks.find(t => !t.done && t.title === d.title); if (t) t.done = true;
      tl(f, 'nota', 'Tarefa concluída: ' + d.title, at);
    } else if (e.tipo === 'supressao') {
      suppress(V, s, f, d.reason, at);
    } else if (e.tipo === 'supressao_removida') {
      V.sup = V.sup.filter(x => !(x.company_id === s.id || (s.cnpj && x.cnpj === s.cnpj)));
      setBoth(s, f, 'suppressed', false); f.blocked_reason = null;
      if (f.stage === 'nao_contatar') { setBoth(s, f, 'stage', 'acompanhar_futuramente'); setBoth(s, f, 'stage_label', STAGE_LABEL.acompanhar_futuramente); }
      tl(f, 'sistema', 'Removida da lista de supressão', at);
    }
  }
  function findCo(V, id) { const s = V.byId[String(id)]; if (!s) fail('Empresa não encontrada.', 404); return s; }
  function tasksOf(V) {
    const now = Date.now(), out = [];
    for (const s of V.comps) {
      const f = V.fichas[String(s.id)]; if (!f) continue;
      for (const t of f.tasks) if (!t.done) out.push({ ...t, overdue: !!(t.due_at && Date.parse(t.due_at) < now), company_id: s.id, company_name: s.name });
    }
    return out.sort((a, b) => (a.due_at || '9').localeCompare(b.due_at || '9'));
  }
  function pipelineOf(V) {
    const groups = Object.fromEntries(STAGES.map(([k]) => [k, []]));
    V.comps.forEach(s => groups[s.stage] && groups[s.stage].push(s));
    return { stages: STAGES.map(([key, label]) => ({ key, label, count: groups[key].length, items: key === 'identificada' ? [] : groups[key] })) };
  }
  function searchOf(V, p) {
    const num = (k) => p.get(k) === null || p.get(k) === '' ? null : Number(p.get(k));
    const q = (p.get('q') || '').toLowerCase(), digits = q.replace(/[^0-9a-z]/g, '');
    let ufs = (p.get('uf') || '').toUpperCase().split(',').map(x => x.trim()).filter(Boolean);
    const region = p.get('region');
    if (region) {
      const r = (D['/regions'] || {})[region]; if (!r) fail('Região inválida.', 400);
      ufs = ufs.length ? r.filter(u => ufs.includes(u)) : r; if (!ufs.length) ufs = r;
    }
    const cnae = (p.get('cnae') || '').replace(/\D/g, ''), debt = p.get('debt_type');
    const debtProfiles = debt ? ((D['/debt-types'] || []).find(x => x.key === debt) || { perfis: [] }).perfis : null;
    const hs = p.get('has_signal'), stage = p.get('stage'), band = p.get('band');
    const [cmin, cmax, ymin, ymax] = ['capital_min', 'capital_max', 'years_min', 'years_max'].map(num);
    const items = V.comps.filter(s => {
      if (q && !((s.name + ' ' + (s.trade_name || '')).toLowerCase().includes(q) || (digits.length >= 8 && (s.cnpj || '').toLowerCase().startsWith(digits)))) return false;
      if (ufs.length && !ufs.includes(s.state)) return false;
      if (p.get('municipio') && !(s.city || '').toLowerCase().includes(p.get('municipio').toLowerCase())) return false;
      if (cnae && !((s.cnae_main || '').startsWith(cnae) || (p.get('cnae_secundario') !== 'false' && ((V.fichas[String(s.id)] || {}).cnae_secondary || []).some(x => String(x).includes(cnae))))) return false;
      if (p.get('profile') && s.profile !== p.get('profile')) return false;
      if (debtProfiles && !debtProfiles.includes(s.profile)) return false;
      if (p.get('size') && s.company_size !== p.get('size').toUpperCase()) return false;
      if (p.get('situacao') && s.registration_status !== p.get('situacao').toUpperCase()) return false;
      if (cmin !== null && !(s.capital_social >= cmin)) return false;
      if (cmax !== null && !(s.capital_social != null && s.capital_social <= cmax)) return false;
      if (ymin !== null && !(s.years_active >= ymin)) return false;
      if (ymax !== null && !(s.years_active != null && s.years_active <= ymax)) return false;
      if (stage && s.stage !== stage) return false;
      if (band && s.band !== band) return false;
      if (hs === 'true' && !s.signals) return false;
      if (hs === 'false' && s.signals) return false;
      if (p.get('include_competitors') !== 'true' && ((s.cnae_main || '').startsWith('8291') || s.band === 'concorrente')) return false;
      if (p.get('include_suppressed') !== 'true' && s.suppressed) return false;
      return true;
    });
    const sort = p.get('sort') || 'score';
    const cmp = { score: (a, b) => b.score - a.score || (b.capital_social || 0) - (a.capital_social || 0),
      capital: (a, b) => (b.capital_social ?? -1) - (a.capital_social ?? -1), name: (a, b) => a.name.localeCompare(b.name),
      opened: (a, b) => (a.opened_at || '9').localeCompare(b.opened_at || '9'), recent: (a, b) => (b.last_signal_at || '').localeCompare(a.last_signal_at || '') }[sort] || (() => 0);
    items.sort(cmp);
    const page = Math.max(1, Number(p.get('page') || 1)), per = Math.min(100, Math.max(1, Number(p.get('per_page') || 25)));
    return { items: items.slice((page - 1) * per, page * per), total: items.length, page, per_page: per, note: null };
  }
  function fichaOut(V, id) {
    const s = findCo(V, id), f = clone(ficha(V, s));
    Object.assign(f, { suppressed: s.suppressed, stage: s.stage, stage_label: s.stage_label, score: s.score, band: s.band, band_label: s.band_label });
    f.id = s.id;
    if (f.pending) f.pending_note = `${f.pending} registro(s) desta empresa entram no cálculo da pontuação na próxima atualização (aos 10 minutos de cada hora).`;
    return f;
  }

  // --- gravação das ações do CRM no banco da página ---
  async function record(tipo, chave, dados) {
    if (!S.db) fail('Salvar no CRM exige a página aberta no claude.ai (banco da página).');
    const ev = { tipo, chave: chave || null, dados: dados || {}, em: new Date().toISOString() };
    let ref;
    try { ref = await S.db.collection('crm_eventos').add(ev); }
    catch (e) { fail(e.code === 'quota_exceeded' ? 'O banco da página está cheio: a versão instalada (servidor próprio) é o caminho para volumes maiores.' : `Não foi possível salvar (${e.code || 'erro'}).`); }
    if (!S.crm.some(x => x.id === ref.id)) S.crm.push({ ...ev, id: ref.id });
    VIEW = null;
    refreshPending();
    return ref.id;
  }
  const isValidCnpj = (v) => {
    const c = String(v || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase();
    if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(c) || new Set(c).size === 1) return false;
    const dv = (base, w) => { const t = [...base].reduce((acc, ch, i) => acc + (ch.charCodeAt(0) - 48) * w[i], 0) % 11; return t < 2 ? '0' : String(11 - t); };
    const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], d1 = dv(c.slice(0, 12), w1), d2 = dv(c.slice(0, 12) + d1, [6, ...w1]);
    return c[12] === d1 && c[13] === d2;
  };
  async function crmWrite(method, route, body) {
    const V = view();
    let m;
    if (method === 'PATCH' && (m = route.match(/^\/companies\/([^/]+)$/))) {
      const s = findCo(V, m[1]), f = ficha(V, s);
      if ('stage' in body) {
        if (!STAGE_LABEL[body.stage]) fail('Etapa inválida.', 400);
        if (body.stage === 'perdido' && !(body.lost_reason || f.lost_reason)) fail("Informe o motivo da perda para marcar como 'Perdido'.", 400);
        if (body.stage !== 'nao_contatar' && s.suppressed) fail('Empresa na lista de supressão: remova-a da lista (Configurações) antes de mudar a etapa.', 409);
      }
      if (body.potential_value != null && body.potential_value < 0) fail('Valor potencial não pode ser negativo.', 400);
      await record('empresa_atualizada', coKey(s), body);
      return fichaOut(view(), s.id);
    }
    if (method === 'POST' && (m = route.match(/^\/companies\/([^/]+)\/interactions$/))) {
      const s = findCo(V, m[1]), f = ficha(V, s);
      if (!KIND_LABEL[body.kind] || ['etapa', 'sistema'].includes(body.kind)) fail('Tipo inválido.', 400);
      if (body.channel && !CHANNELS.has(body.channel)) fail('Canal inválido.', 400);
      if (!body.summary || body.summary.length < 2) fail('Descreva o que aconteceu.', 400);
      if (OUTREACH.has(body.kind)) {
        if (s.suppressed || s.stage === 'nao_contatar') fail(f.blocked_reason || "Empresa marcada como 'Não contatar'.", 409);
        const gap = Number(V.settings.dias_entre_contatos || 7), lo = f.last_outreach_at;
        if (lo && !body.confirm_repeat && Date.now() - Date.parse(lo) < gap * 864e5)
          fail(`Último contato em ${ddmm(lo)}, há menos de ${gap} dias. Confirme para registrar outro contato (evita abordagens repetidas).`, 409);
      }
      const { confirm_repeat, ...dados } = body;
      await record('interacao', coKey(s), dados);
      const st = view().byId[String(s.id)];
      return { id: 'p', stage: st.stage, stage_label: st.stage_label };
    }
    if (method === 'POST' && (m = route.match(/^\/companies\/([^/]+)\/tasks$/))) {
      const s = findCo(V, m[1]);
      if (!body.title || body.title.length < 2) fail('Informe a tarefa.', 400);
      await record('tarefa', coKey(s), body);
      return { id: 'p' };
    }
    if (method === 'PATCH' && (m = route.match(/^\/tasks\/(.+)$/))) {
      const t = tasksOf(V).find(x => String(x.id) === m[1]); if (!t) fail('Tarefa não encontrada.', 404);
      if (body.done) await record('tarefa_concluida', coKey(V.byId[String(t.company_id)]), { title: t.title, due_at: t.due_at });
      return { id: t.id, done: true };
    }
    if (method === 'POST' && route === '/companies') {
      const cnpj = (body.cnpj || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase() || null;
      if (cnpj && !isValidCnpj(cnpj)) fail('CNPJ inválido.', 400);
      const dup = cnpj ? V.comps.find(c => c.cnpj === cnpj) : V.comps.find(c => c.name.toLowerCase() === (body.name || '').toLowerCase());
      if (dup) fail(`Empresa já cadastrada (id ${dup.id}): ${dup.name}.`, 409);
      const dados = { ...body, cnpj, state: (body.state || '').toUpperCase() || null };
      const id = await record('empresa_criada', cnpj || 'nome:' + body.name, dados);
      return fichaOut(view(), 'novo-' + id);
    }
    if (method === 'POST' && route === '/suppression') {
      const s = body.company_id ? findCo(V, body.company_id) : (body.cnpj ? V.comps.find(c => c.cnpj === String(body.cnpj).replace(/[^0-9A-Za-z]/g, '').toUpperCase()) : null);
      const cnpj = s ? s.cnpj : String(body.cnpj || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase();
      if (!s && !cnpj) fail('Informe a empresa ou o CNPJ.', 400);
      if (V.sup.some(x => (s && x.company_id === s.id) || (cnpj && x.cnpj === cnpj))) fail('Empresa já está na lista de supressão.', 409);
      await record('supressao', s ? coKey(s) : cnpj, { cnpj, reason: body.reason || '' });
      return { id: 'p' };
    }
    if (method === 'DELETE' && (m = route.match(/^\/suppression\/(.+)$/))) {
      const x = V.sup.find(y => String(y.id) === m[1]); if (!x) fail('Registro não encontrado.', 404);
      const s = x.company_id != null ? V.byId[String(x.company_id)] : V.comps.find(c => x.cnpj && c.cnpj === x.cnpj);
      await record('supressao_removida', s ? coKey(s) : x.cnpj, { cnpj: x.cnpj });
      return { ok: true };
    }
    if (method === 'PUT' && route === '/settings') {
      const d = { ...body };
      if (d.ufs_atuacao) { const bad = d.ufs_atuacao.filter(u => !UFS.has(u)); if (bad.length) fail('UF inválida: ' + bad.join(', '), 400); }
      if (d.dias_entre_contatos != null && !(d.dias_entre_contatos >= 1 && d.dias_entre_contatos <= 90)) fail('Dias entre contatos: de 1 a 90.', 400);
      await record('config', null, d);
      return view().settings;
    }
    return undefined;
  }

  function refreshPending() {
    const el = document.getElementById('lc-pending'); if (!el) return;
    const n = pending().length;
    el.innerHTML = n ? `<b>${n} registro(s) do CRM</b> já salvos entram no recálculo da pontuação e dos painéis na próxima atualização.` : '';
  }

  // --- laboratório de negociação (mesma regra de backend/app/services/negotiation.py) ---
  function simulate(p) {
    const valor = Number(p.valor_original); if (!(valor > 0)) fail('Valor original deve ser positivo.', 400);
    const d = (s) => { const t = Date.parse(s + 'T00:00:00Z'); if (isNaN(t)) fail('Data inválida.', 400); return t; };
    const venc = d(p.vencimento), base = d(p.data_base), dias = Math.max(0, Math.round((base - venc) / 864e5)), meses = dias / 30;
    const pc = (k) => Number(p[k] || 0) / 100;
    const [mp, jp, cp, dp, jparc] = [pc('multa_pct'), pc('juros_mes_pct'), pc('correcao_pct'), pc('desconto_pct'), pc('juros_parcelamento_mes_pct')];
    if (Math.min(mp, jp, dp, jparc) < 0 || dp > 1) fail('Percentuais inválidos.', 400);
    const comp = p.juros_tipo === 'composto';
    const correcao = dias ? valor * cp : 0, corr = valor + correcao, multa = dias ? corr * mp : 0;
    const juros = comp ? corr * (Math.pow(1 + jp, meses) - 1) : corr * jp * meses;
    const total = corr + multa + juros, enc = correcao + multa + juros, sobre = p.desconto_sobre || 'encargos';
    const desconto = (sobre === 'encargos' ? enc : total) * dp, acordado = total - desconto, entrada = Number(p.entrada || 0);
    if (entrada < 0 || entrada > acordado) fail('Entrada deve estar entre zero e o valor acordado.', 400);
    const n = Math.round(Number(p.parcelas || 1)); if (!(n >= 1 && n <= 120)) fail('Parcelas: de 1 a 120.', 400);
    const saldo = acordado - entrada, parcela = jparc > 0 ? saldo * jparc / (1 - Math.pow(1 + jparc, -n)) : saldo / n;
    const r = (x) => Math.round(x * 100) / 100, f2 = (x) => x.toFixed(2), br = (t) => new Date(t).toLocaleDateString('pt-BR', { timeZone: 'UTC' });
    const avisos = ['Todas as taxas e índices foram informados por você; o sistema não presume nenhum.',
      'Confira no contrato e na legislação aplicável os limites de multa, juros e correção. [NECESSÁRIO CONFERIR]'];
    if (!(mp || jp || cp)) avisos.unshift('Nenhum encargo informado: o total considera só o valor original.');
    return { dias_atraso: dias, meses_considerados: r(meses), valor_original: r(valor), correcao: r(correcao), valor_corrigido: r(corr),
      multa: r(multa), juros: r(juros), total_atualizado: r(total), desconto: r(desconto), valor_acordado: r(acordado), entrada: r(entrada),
      parcelas: n, valor_parcela: r(parcela), total_a_receber: r(entrada + parcela * n),
      memoria: [`Atraso: ${dias} dia(s) entre ${br(venc)} e ${br(base)} (${meses.toFixed(2)} meses de 30 dias).`,
        `Correção informada: ${(cp * 100).toFixed(2)}% sobre o original = ${f2(correcao)}.`,
        `Multa informada: ${(mp * 100).toFixed(2)}% sobre o valor corrigido = ${f2(multa)}.`,
        `Juros informados: ${(jp * 100).toFixed(2)}% ao mês, ${comp ? 'compostos' : 'simples'} = ${f2(juros)}.`,
        `Desconto: ${(dp * 100).toFixed(2)}% sobre ${sobre === 'encargos' ? 'os encargos' : 'o total'} = ${f2(desconto)}.`,
        `Parcelamento: entrada ${f2(entrada)} + ${n} parcela(s) de ${f2(parcela)}` + (jparc ? ` (juros de ${(jparc * 100).toFixed(2)}% a.m., tabela Price).` : ' (sem juros).')],
      avisos };
  }

  // --- busca ao vivo: dispara a tarefa agendada na nuvem ---
  async function requestRefresh(what) {
    if (!META.trigger_id) fail('Esta página não tem a tarefa de atualização configurada.');
    if (!S.mcp) fail('A busca ao vivo funciona com a página aberta no claude.ai (conector Claude Code Remote). Aqui ela não está disponível.');
    if (S.db) {
      try {
        const snap = await S.db.doc('estado/atualizacao').get();
        const t = snap.exists && Date.parse(snap.data().pedidoEm);
        if (t && Date.now() - t < 8 * 60e3) fail(`Já há uma atualização em andamento (pedida às ${hhmm(new Date(t))}). A página recarrega sozinha quando terminar.`);
      } catch (e) { if (String(e.message).startsWith('{')) throw e; }
    }
    try {
      await S.mcp.callTool('Claude Code Remote', 'fire_trigger', { trigger_id: META.trigger_id });
    } catch (e) {
      const msg = {
        needs_reauth: 'Reconecte o conector Claude Code Remote em claude.ai → Configurações → Conectores e tente de novo.',
        server_not_connected: 'Adicione o conector Claude Code Remote em claude.ai → Configurações → Conectores para usar a busca ao vivo.',
        selection_required: 'Escolha qual conector Claude Code Remote usar no aviso do claude.ai e tente de novo.',
        not_in_manifest: 'A busca ao vivo precisa da sua permissão para o conector Claude Code Remote (menu Permissões da página).',
        approval_required: 'A busca ao vivo precisa da sua aprovação: clique de novo e permita o acesso quando o claude.ai pedir.',
        blocked_by_policy: 'A política da sua organização bloqueia o disparo de tarefas por esta página.',
        tool_error: 'A tarefa de atualização não pôde ser disparada: ' + String(e.message || '').slice(0, 160),
        server_unavailable: 'O serviço de tarefas não respondeu agora. Confira em alguns minutos se a página atualizou antes de clicar de novo.',
      }[e.code] || `Não foi possível pedir a atualização (${e.code || 'erro'}). Tente de novo em instantes.`;
      fail(msg);
    }
    if (S.db) S.db.doc('estado/atualizacao').set({ pedidoEm: new Date().toISOString(), pedido: what }).catch(() => {});
    fail(`Busca pedida às ${hhmm(new Date())}. Ela roda na nuvem (${what}) e a página recarrega sozinha com os dados novos em 3 a 6 minutos.`);
  }

  async function api(path, opt = {}) {
    const method = (opt.method || 'GET').toUpperCase();
    const [route, qs] = path.split('?'); const p = new URLSearchParams(qs || '');
    if (method === 'GET') {
      const V = view();
      if (route === '/dashboard/summary') return summary();
      if (route === '/opportunities') { const st = p.get('status'); return allOpps().filter(o => st ? o.status === st : o.status !== 'discarded'); }
      if (route === '/companies/search') return searchOf(V, p);
      if (route === '/pipeline') return pipelineOf(V);
      if (route === '/tasks') return tasksOf(V);
      if (route === '/settings') return V.settings;
      if (route === '/suppression') return V.sup;
      if (route === '/daily-intelligence') {
        const d = clone(D['/daily-intelligence?limit=5'] || { itens: [], metodo: '' });
        const gap = Number(V.settings.dias_entre_contatos || 7) * 864e5;
        d.itens = d.itens.filter(x => { const s = V.byId[String(x.id)], f = V.fichas[String(x.id)] || {};
          return s && !s.suppressed && !['cliente_conquistado', 'perdido', 'nao_contatar', 'acompanhar_futuramente'].includes(s.stage)
            && !(f.last_outreach_at && Date.now() - Date.parse(f.last_outreach_at) < gap); })
          .map(x => ({ ...x, stage: V.byId[String(x.id)].stage, stage_label: V.byId[String(x.id)].stage_label }));
        return d;
      }
      let m;
      if ((m = route.match(/^\/companies\/([^/]+)\/approach$/))) {
        const s = findCo(V, m[1]);
        if (s.suppressed || s.stage === 'nao_contatar') fail('Empresa na lista de supressão: nenhuma abordagem é gerada.', 409);
        const a = (D.approaches || {})[String(s.id)];
        if (!a) fail('A abordagem desta empresa é gerada na próxima atualização (aos 10 minutos de cada hora).', 404);
        return a;
      }
      if (route === '/contacts') {
        const all = (D['/contacts'] || { items: [] }).items, q = (p.get('q') || '').toLowerCase(), kind = p.get('kind');
        const items = all.filter(x => { const s = V.byId[String(x.company_id)];
          return !(s && s.suppressed) && (!kind || x.kind === kind) && (!q || (x.company_name + ' ' + (x.cnpj || '') + ' ' + x.value).toLowerCase().includes(q)); });
        return { total: items.length, items: items.slice(0, 100) };
      }
      if (route === '/portfolios') return [];
      if (route.startsWith('/portfolios/')) fail('Carteiras de clientes ficam só na versão instalada.', 404);
      if ((m = route.match(/^\/companies\/([^/]+)$/))) return fichaOut(V, m[1]);
      if (route === '/market/datajud') {
        const k = `/market/datajud?uf=${(p.get('uf') || '').toUpperCase()}`;
        if (k in D) return D[k];
        fail(S.ufs.includes(p.get('uf')) ? 'Mapa desta UF pedido: aparece na próxima atualização.' : 'Sem mapa desta UF ainda. Clique em "Atualizar pelo DataJud" para incluí-la.', 404);
      }
      if (route.startsWith('/cnpj/')) fail('A consulta de CNPJ funciona na versão instalada: esta página não pode acessar sites externos.');
      if (path in D) return D[path];
      if (route in D) return D[route];
      fail('Indisponível nesta página.', 404);
    }
    const body = JSON.parse(opt.body || '{}');
    const crm = await crmWrite(method, route, body);
    if (crm !== undefined) return crm;
    if (route.startsWith('/agents/run/')) {
      const id = Number(route.split('/').pop()); const o = allOpps().find(x => x.id === id);
      if (!o) fail('Oportunidade não encontrada.');
      const r = runPipeline(o);
      o.status = r.qualification.recommended_status; o.score = r.qualification.score; o.score_reason = r.qualification.reason;
      if (S.db) {
        try { await S.db.doc('agentes/' + keyOf(o)).set({ status: o.status, score: o.score, score_reason: o.score_reason, issues: r.audit.issues, at: new Date().toISOString() }); }
        catch (e) { fail(`Os agentes rodaram, mas o resultado não foi salvo (${e.code || 'erro'}).`); }
      }
      return { opportunity: o, agents: r };
    }
    if (route === '/opportunities') {
      if (!S.db) fail('Salvar oportunidades exige a página aberta no claude.ai.');
      const d = body;
      if (!d.company_name || !d.title || !d.evidence) fail('Preencha empresa, título e evidência.');
      const [score, reason] = scoreOpportunity(d.kind, d.description, d.evidence, d.source_url);
      const doc = { company_name: d.company_name, cnpj: d.cnpj || null, segment: d.segment || null, city: d.city || null, state: (d.state || '').toUpperCase() || null,
        kind: d.kind, title: d.title, description: d.description || '', evidence: d.evidence, source_name: d.source_name || 'Cadastro manual',
        source_url: d.source_url || null, score, score_reason: reason, status: 'review', commercial_signal: 'sinal_a_confirmar', criadoEm: new Date().toISOString() };
      try { await S.db.collection('oportunidades_manuais').add(doc); }
      catch (e) { fail(e.code === 'quota_exceeded' ? 'O banco da página está cheio: apague oportunidades antigas.' : `Não foi possível salvar (${e.code || 'erro'}).`); }
      return doc;
    }
    if (route === '/capture/pncp') return requestRefresh('editais PNCP, vagas e DataJud');
    if (route === '/capture/jobs') return requestRefresh('vagas, editais PNCP e DataJud');
    if (route === '/market/datajud') {
      const uf = (p.get('uf') || '').toUpperCase();
      if (S.db && uf && !S.ufs.includes(uf)) {
        const ufs = [...new Set([...S.ufs, uf])].slice(-5);
        try { await S.db.doc('config/ufs').set({ ufs }); } catch (e) { fail(`Não foi possível registrar a UF (${e.code || 'erro'}).`); }
      }
      return requestRefresh(`mapa do DataJud${uf ? ' de ' + uf : ''}`);
    }
    if (route === '/negotiation/simulate') return simulate(body);
    if (route === '/portfolios') fail('Por segurança, carteiras de títulos (dados de devedores de terceiros) não são enviadas para a página publicada. Use a versão instalada para a inteligência de cobrança.');
    if (route === '/contacts/sync') fail('Nesta página a sincronização de contatos roda sozinha a cada atualização (aos 10 minutos de cada hora).');
    if (route === '/contacts') fail('Cadastro de contato funciona na versão instalada.');
    if (route.endsWith('/enrich')) fail('A consulta de CNPJ funciona na versão instalada: esta página não pode acessar sites externos.');
    fail('Ação indisponível nesta página.');
  }

  // recursos da página: ligam quando o claude.ai responder; sem eles a página continua legível
  (async () => {
    if (!window.claude || !window.claude.use) return;
    const [db, mcp] = await Promise.all([claude.use('db'), claude.use('mcp')]);
    S.mcp = mcp; S.db = db;
    if (!db) return;
    const rerender = () => { VIEW = null; refreshPending(); try { load(); } catch (_) {} };
    db.collection('agentes').onSnapshot(s => { S.agents = Object.fromEntries(s.docs.map(d => [d.id, d.data()])); rerender(); }, () => {});
    db.collection('oportunidades_manuais').onSnapshot(s => { S.manual = s.docs.map(d => ({ ...d.data(), _doc: d.id })); rerender(); }, () => {});
    db.collection('crm_eventos').onSnapshot(s => { S.crm = s.docs.map(d => ({ ...d.data(), id: d.id })); S.crmLoaded = true; rerender(); }, () => {});
    db.doc('config/ufs').onSnapshot(s => { S.ufs = (s.exists && s.data().ufs) || []; }, () => {});
  })();
  if (META.crm_falhas && META.crm_falhas.length) console.warn('Ações do CRM não reaplicadas nesta atualização:', META.crm_falhas);

  return { api, state: S };
})();
