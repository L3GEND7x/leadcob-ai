let assistantConversation = null;
let assistantBusy = false;
async function viewAssistente() {
  const [status, history] = await Promise.all([api('/assistant/status'), api('/assistant/conversations')]);
  V().innerHTML = head('SEU AMBIENTE DE TRABALHO', 'Assistente LeadCob', 'Consulte dados, prepare abordagens e organize sua próxima ação.')
    + `<div class="assistant-layout"><section class="panel"><button id="ai-new">Nova conversa</button><div class="rows">${history.map(c => `<button class="row" data-conversation="${esc(c.id)}">${esc(c.title)}</button>`).join('')}</div><p class="note">${esc(status.model || 'Modelo não configurado')}<br>Consumo estimado e reservado US$ ${Number(status.estimated_and_reserved_usd).toFixed(4)} / ${Number(status.budget_usd).toFixed(2)}</p>${!status.configured ? `<p class="warnbox">${esc(status.setup)}</p>` : ''}</section>
    <section class="panel"><div id="ai-messages" aria-live="polite"></div><div id="ai-actions"></div><form id="ai-form" class="form"><label class="f full">Como posso ajudar?<textarea name="message" maxlength="6000" required placeholder="O que preciso fazer hoje?"></textarea></label><button class="primary" ${status.configured ? '' : 'disabled'}>Enviar</button><p id="ai-state" role="status"></p></form><button id="ai-delete" class="small">Excluir conversa</button></section></div>`;
  document.querySelectorAll('[data-conversation]').forEach(b => b.onclick = () => openAssistantConversation(b.dataset.conversation));
  $('ai-new').onclick = () => { assistantConversation = null; $('ai-messages').replaceChildren(); $('ai-actions').replaceChildren(); };
  $('ai-delete').onclick = async () => {
    if (assistantConversation && confirm('Excluir esta conversa e suas ações pendentes?')) {
      await send('/assistant/conversations/' + assistantConversation, 'DELETE'); assistantConversation = null; viewAssistente();
    }
  };
  $('ai-form').onsubmit = async event => {
    event.preventDefault(); if (assistantBusy) return;
    const form = event.target, text = form.message.value.trim();
    if (!text) return;
    assistantBusy = true; form.querySelector('button').disabled = true; $('ai-state').textContent = 'Consultando seus dados…';
    const requestId = crypto.randomUUID();
    try {
      const data = await send('/assistant/messages', 'POST', {conversation_id: assistantConversation, request_id: requestId, message: text});
      assistantConversation = data.id; form.message.value = ''; renderAssistantConversation(data);
      $('ai-state').textContent = 'Resposta salva.';
    } catch (error) { $('ai-state').textContent = errMsg(error, 'Falha de conexão. Confira o histórico antes de reenviar.'); }
    finally { assistantBusy = false; form.querySelector('button').disabled = false; }
  };
  if (assistantConversation) await openAssistantConversation(assistantConversation);
}
async function openAssistantConversation(id) {
  assistantConversation = id; renderAssistantConversation(await api('/assistant/conversations/' + id));
}
function renderAssistantConversation(data) {
  $('ai-messages').innerHTML = data.messages.map(m => `<article class="ai-message"><small>${m.role === 'user' ? 'Você' : 'Assistente LeadCob'}</small><p>${esc(m.text).replace(/#\/(empresa|cobranca)\/(\d+)/g, '<a href="#/$1/$2">Abrir registro $2</a>')}</p></article>`).join('');
  $('ai-actions').innerHTML = data.actions.map(a => `<article class="warnbox"><b>Tarefa proposta · ${esc(a.status)}</b><p>${esc(a.payload.title)} · Empresa ${esc(a.payload.company_id)} · ${esc(a.payload.due_at || 'sem prazo')}</p>${a.status === 'pending' ? `<button data-approve="${esc(a.id)}">Confirmar criação</button> <button data-reject="${esc(a.id)}">Recusar</button>` : ''}</article>`).join('');
  document.querySelectorAll('[data-approve]').forEach(b => b.onclick = async () => { b.disabled = true; try { await send('/assistant/actions/' + b.dataset.approve + '/confirm', 'POST'); await openAssistantConversation(data.id); } catch (e) { toast(errMsg(e), 7000, true); b.disabled = false; } });
  document.querySelectorAll('[data-reject]').forEach(b => b.onclick = async () => { await send('/assistant/actions/' + b.dataset.reject + '/reject', 'POST'); await openAssistantConversation(data.id); });
}
