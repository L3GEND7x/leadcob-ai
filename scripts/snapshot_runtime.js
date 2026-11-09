/* LeadCob — camada da página publicada (claude.ai).
 *
 * Substitui a função api() do frontend. Lê os dados embutidos (window.__DEMO)
 * e usa os recursos da página publicada:
 *  - db: guarda resultados dos agentes, oportunidades cadastradas à mão,
 *        UFs pedidas para o mapa do DataJud e o horário do último pedido de busca;
 *  - mcp (conector "Claude Code Remote", ferramenta fire_trigger): dispara a tarefa
 *        agendada que busca os dados ao vivo e republica a página.
 * Sem esses recursos (arquivo aberto fora do claude.ai), a página continua legível.
 */
const LC = (() => {
  const D = window.__DEMO, META = D.__meta || {};
  const S = { db: null, mcp: null, agents: {}, manual: [], ufs: [] };
  const fail = (detail) => { throw Error(JSON.stringify({ detail })); };
  const hhmm = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  const keyOf = (o) => (o.source_key || ('manual:' + o._doc)).replace(/[^A-Za-z0-9_.~:@+-]/g, '_').slice(0, 190);

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

  // --- dados combinados: coleta embutida + banco da página ---
  function allOpps() {
    const base = D['/opportunities'].map(o => ({ ...o }));
    S.manual.forEach((m, i) => base.push({ ...m, id: 900000 + i }));
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
      prospects: (D.prospects_all || []).length,
      average_score: ops.length ? Math.round(10 * ops.reduce((t, o) => t + o.score, 0) / ops.length) / 10 : 0,
    });
    return s;
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
      if (route === '/dashboard/summary') return summary();
      if (route === '/opportunities') { const st = p.get('status'); return allOpps().filter(o => st ? o.status === st : o.status !== 'discarded'); }
      if (route === '/prospects') {
        const q = (p.get('q') || '').toLowerCase(), seg = p.get('segment'), uf = (p.get('uf') || '').toUpperCase(), size = p.get('size');
        return (D.prospects_all || []).filter(c => (!seg || c.target_profile === seg) && (!uf || c.state === uf) && (!size || c.company_size === size)
          && (!q || (c.name + ' ' + (c.trade_name || '') + ' ' + (c.cnpj || '')).toLowerCase().includes(q)) && !(c.cnae_main || '').startsWith('8291'));
      }
      if (route === '/market/datajud') {
        const k = `/market/datajud?uf=${(p.get('uf') || '').toUpperCase()}`;
        if (k in D) return D[k];
        fail(S.ufs.includes(p.get('uf')) ? 'Mapa desta UF pedido: aparece na próxima atualização.' : 'Sem mapa desta UF ainda. Clique em "Atualizar pelo DataJud" para incluí-la.');
      }
      if (route.startsWith('/cnpj/')) fail('A consulta de CNPJ funciona na versão instalada: esta página não pode acessar sites externos.');
      if (path in D) return D[path];
      if (route in D) return D[route];
      fail('Indisponível nesta página.');
    }
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
      const d = JSON.parse(opt.body || '{}');
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
    if (route.startsWith('/companies/')) fail('A consulta de CNPJ funciona na versão instalada: esta página não pode acessar sites externos.');
    fail('Ação indisponível nesta página.');
  }

  // recursos da página: liga quando o claude.ai responder; sem eles a página continua legível
  (async () => {
    if (!window.claude || !window.claude.use) return;
    const [db, mcp] = await Promise.all([claude.use('db'), claude.use('mcp')]);
    S.mcp = mcp; S.db = db;
    if (!db) return;
    const rerender = () => { try { load(); } catch (_) {} };
    db.collection('agentes').onSnapshot(s => { S.agents = Object.fromEntries(s.docs.map(d => [d.id, d.data()])); rerender(); }, () => {});
    db.collection('oportunidades_manuais').onSnapshot(s => { S.manual = s.docs.map(d => ({ ...d.data(), _doc: d.id })); rerender(); }, () => {});
    db.doc('config/ufs').onSnapshot(s => { S.ufs = (s.exists && s.data().ufs) || []; }, () => {});
  })();

  return { api, state: S };
})();
