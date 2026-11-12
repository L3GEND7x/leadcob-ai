async function viewAgenda() {
  const tasks = await api('/tasks?status=all');
  V().innerHTML = head('ACOMPANHAMENTO', 'Agenda comercial', 'Tarefas abertas, atrasadas e concluídas. Datas no horário do seu dispositivo.')
    + panel('Atividades', '', tasks.map(t => `<article class="task"><div class="main"><strong>${esc(t.title)}</strong><small>${esc(t.company_name || '')} · ${t.done ? 'Concluída' : t.overdue ? 'Atrasada' : 'Pendente'}</small><input type="datetime-local" data-task-date="${t.id}" value="${toLocalInput(t.due_at)}"></div><button data-save-task="${t.id}">Reagendar</button><button data-done-task="${t.id}" data-done="${!t.done}">${t.done ? 'Reabrir' : 'Concluir'}</button></article>`).join('') || '<p>Nenhuma tarefa.</p>');
  document.querySelectorAll('[data-save-task]').forEach(b => b.onclick = async () => {
    await send('/tasks/' + b.dataset.saveTask, 'PATCH', {due_at: fromLocalInput(document.querySelector(`[data-task-date="${b.dataset.saveTask}"]`).value)}); viewAgenda();
  });
  document.querySelectorAll('[data-done-task]').forEach(b => b.onclick = async () => {
    await send('/tasks/' + b.dataset.doneTask, 'PATCH', {done: b.dataset.done === 'true'}); viewAgenda();
  });
}

async function searchDomain(id) {
  const box = $('domain-candidates');
  box.textContent = 'Pesquisando candidatos…';
  try {
    const data = await send('/contacts/domain-search/' + id, 'POST');
    if (data.automatic_available === false) {
      box.innerHTML = `<p class="note">${esc(data.note)}</p><a class="btn" href="${esc(safeHttpUrl(data.search_url))}" target="_blank" rel="noopener noreferrer">Pesquisar site e contatos</a>`;
      return;
    }
    box.innerHTML = data.items.length ? data.items.map(item => `<div class="task"><div class="main"><strong>${esc(item.website)}</strong><small>${esc(item.evidence)} · ${esc(item.status)}</small><a href="${esc(safeHttpUrl(item.source_url))}" target="_blank" rel="noopener">Conferir fonte</a></div><button data-domain="${item.id}">Confirmar este site</button></div>`).join('') : '<p>Nenhum domínio candidato encontrado.</p>';
    box.querySelectorAll('[data-domain]').forEach(button => button.onclick = async () => {
      if (!confirm('Você conferiu que este domínio pertence à empresa?')) return;
      try { await send('/contacts/domain-candidates/' + button.dataset.domain + '/confirm', 'POST'); viewEmpresa(id); }
      catch (error) { toast(errMsg(error), 7000, true); }
    });
  } catch (error) { box.textContent = errMsg(error, 'Não foi possível pesquisar.'); }
}

async function showPortfolioPreview(body) {
  const preview = await send('/portfolios/preview', 'POST', body);
  const box = $('portfolio-preview');
  box.innerHTML = `<div class="warnbox"><b>Confira antes de gravar</b><p>${fmt(preview.valid_count)} títulos válidos · ${money(preview.total)} · ${fmt(preview.error_count)} linhas inválidas · ${fmt(preview.possible_duplicates.length)} possíveis duplicidades.</p>
    ${preview.errors.length ? `<p>Erros: ${preview.errors.slice(0, 8).map(e => `linha ${e.linha}: ${esc(e.erro)}`).join(' · ')}</p>` : ''}
    ${preview.possible_duplicates.length ? `<p>Linhas repetidas: ${preview.possible_duplicates.slice(0, 12).map(esc).join(', ')}</p>` : ''}
    <label><input type="checkbox" id="allow-partial" ${preview.error_count ? '' : 'disabled'}> Aceito importar apenas linhas válidas</label><br>
    <label><input type="checkbox" id="allow-duplicates" ${preview.possible_duplicates.length ? '' : 'disabled'}> Revisei e aceito as linhas possivelmente duplicadas</label><br>
    <button class="primary" id="confirm-import">Confirmar importação</button></div>`;
  $('confirm-import').onclick = async () => {
    if (preview.error_count && !$('allow-partial').checked || preview.possible_duplicates.length && !$('allow-duplicates').checked) {
      toast('Revise e confirme as ressalvas antes de importar.', 6000, true); return;
    }
    $('confirm-import').disabled = true;
    try {
      const data = await send('/portfolios', 'POST', {...body, accept_partial: $('allow-partial').checked,
        accept_duplicates: $('allow-duplicates').checked});
      toast(data.reused ? 'Essa carteira já foi importada.' : 'Carteira salva e analisada.');
      location.hash = '#/cobranca/' + data.id;
    } catch (error) { $('confirm-import').disabled = false; toast(errMsg(error), 7000, true); }
  };
}

function renderPortfolioItems(portfolio) {
  const box = $('portfolio-items');
  if (!box) return;
  const items = portfolio.items || [];
  box.innerHTML = panel('Títulos e movimentações', `${items.length} exibidos · dados na posição ${esc(portfolio.data_referencia)}`,
    items.map(item => `<details class="task"><summary>${esc(item.ref || 'Sem referência')} · ${money(item.amount)} · vence ${esc(item.due_date)}</summary>
      <div>${item.events.map(e => `<p>${esc(e.kind)} · ${money(e.amount)} · ${esc(e.effective_date)} · ${esc(e.reference)}</p>`).join('') || '<p>Sem movimentações.</p>'}</div>
      <form data-item="${item.id}" class="form"><select name="kind"><option value="payment">Pagamento</option><option value="discount">Abatimento</option></select><input name="amount" type="number" min="0.01" step="0.01" placeholder="Valor" required><input name="effective_date" type="date" required><input name="reference" placeholder="Comprovante ou autorização" required><button>Registrar</button></form>
      ${item.events.filter(e => e.kind !== 'reversal' && !item.events.some(r => r.reversal_of === e.id)).map(e => `<button data-reverse="${e.id}">Estornar ${money(e.amount)}</button>`).join('')}</details>`).join('') || '<p>Sem títulos.</p>');
  box.querySelectorAll('[data-item]').forEach(form => form.onsubmit = async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    if (!confirm(`Registrar ${data.kind === 'payment' ? 'pagamento' : 'abatimento'} de ${money(data.amount)} para este título?`)) return;
    try { await send(`/portfolios/${portfolio.id}/items/${form.dataset.item}/movements`, 'POST',
      {...data, amount: Number(data.amount), request_id: crypto.randomUUID()}); viewCarteira(portfolio.id); }
    catch (error) { toast(errMsg(error), 7000, true); }
  });
  box.querySelectorAll('[data-reverse]').forEach(button => button.onclick = async () => {
    const reference = prompt('Referência do estorno, como autorização ou comprovante');
    if (!reference || !confirm('Confirma o estorno desta movimentação?')) return;
    try { await send(`/portfolios/${portfolio.id}/movements/${button.dataset.reverse}/reverse`, 'POST',
      {effective_date: new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()), reference, request_id: crypto.randomUUID()}); viewCarteira(portfolio.id); }
    catch (error) { toast(errMsg(error), 7000, true); }
  });
}
