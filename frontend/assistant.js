let assistantConversation = null;
let assistantBusy = false;
const assistantFailureMessages = {provider_quota:'Limite ou saldo da API atingido. Confira o faturamento no provedor.', provider_model:'Modelo indisponível. Confira o modelo configurado e as permissões do projeto.', provider_auth:'Credenciais ou permissões da API recusadas. Confira a configuração do servidor.', provider_rate_limit:'Limite de requisições da API atingido. Confira o histórico antes de tentar novamente.', provider_connection:'Falha de comunicação com o provedor. Confira o histórico antes de reenviar.', request_failed:'Não foi possível concluir. Confira o histórico e as ações pendentes.'};
const assistantConfigLabels = {api_key:'Chave da API',model:'Modelo',monthly_budget:'Orçamento mensal',input_price:'Preço de entrada',output_price:'Preço de saída'};
async function viewAssistente() {
  const [status, history] = await Promise.all([api('/assistant/status'), api('/assistant/conversations')]);
  if (assistantBusy) return;
  const missing = Object.entries(status.configuration_checks || {}).filter(([,ok]) => !ok).map(([k]) => assistantConfigLabels[k] || k);
  V().innerHTML = head('SEU AMBIENTE DE TRABALHO', 'Assistente LeadCob', 'Consulte dados, prepare abordagens e organize sua próxima ação.')
    + `<div class="assistant-layout"><section class="panel"><button id="ai-new">Nova conversa</button><div class="rows">${history.map(c => `<button class="row" data-conversation="${esc(c.id)}">${esc(c.title)}</button>`).join('')}</div><p class="note">${esc(status.model || 'Modelo não configurado')}<br>Consumo estimado e reservado US$ ${Number(status.estimated_and_reserved_usd).toFixed(4)} / ${Number(status.budget_usd).toFixed(2)}</p>${!status.configured ? `<p class="warnbox">${esc(status.setup)} ${esc(missing.join(' · '))}</p>` : '<p class="note">Configuração local presente; conexão ainda não verificada nesta consulta.</p>'}${status.configured ? '<button type="button" id="ai-provider-check">Verificar acesso ao modelo</button><p class="note" id="ai-provider-result" role="status"></p><button type="button" id="ai-generation-check">Testar resposta real da IA</button><p class="note" id="ai-generation-result" role="status"></p>' : ''}</section>
    <section class="panel"><div id="ai-messages" aria-live="polite"></div><div id="ai-actions"></div><form id="ai-form" class="form"><label class="f full">Como posso ajudar?<textarea name="message" maxlength="6000" required placeholder="O que preciso fazer hoje?"></textarea></label><button class="primary" ${status.configured ? '' : 'disabled'}>Enviar</button><p id="ai-state" role="status"></p></form><button id="ai-delete" class="small">Excluir conversa</button></section></div>`;
  const check = $('ai-provider-check');
  if(check) check.onclick = async () => {
    if(assistantBusy) return;
    const result = $('ai-provider-result');
    check.disabled = true;
    result.textContent = 'Consultando metadados do modelo…';
    try {
      const data = await send('/assistant/provider-check', 'POST', {});
      if(!result.isConnected) return;
      result.textContent = (data.model_accessible
        ? 'Modelo acessível nesta consulta. Geração e ferramentas ainda não testadas.'
        : (assistantFailureMessages[data.failure_category] || assistantFailureMessages.request_failed))
        + ' · ' + data.observed_at;
    } catch(error) { if(result.isConnected) result.textContent = errMsg(error, 'Não foi possível verificar o modelo.'); }
    finally { check.disabled = false; }
  };
  const generate = $('ai-generation-check');
  if(generate) generate.onclick = async () => {
    if(assistantBusy || !confirm('Executar uma solicitação real à OpenAI? O teste usa apenas uma frase sintética, consome orçamento da API e não acessa dados do CRM.')) return;
    assistantBusy = true; generate.disabled = true;
    const result = $('ai-generation-result');
    result.textContent = 'Testando geração real…';
    try {
      const data = await send('/assistant/generation-check', 'POST', {});
      if (!result.isConnected) return;
      result.textContent = (data.generation_passed ? 'Geração sintética aprovada. Ferramentas ainda não testadas.' :
        (data.failure_category === 'unexpected_probe_response' ? 'Resposta diferente do esperado; confira modelo e limite de saída.' : assistantFailureMessages[data.failure_category] || assistantFailureMessages.request_failed))
        + ' · Tokens observados: ' + data.input_tokens + ' entrada / ' + data.output_tokens + ' saída.';
    } catch(error) { if(result.isConnected) result.textContent = errMsg(error, 'Não foi possível validar a geração.'); }
    finally { assistantBusy = false; generate.disabled = false; }
  };
  document.querySelectorAll('[data-conversation]').forEach(b => b.onclick = () => openAssistantConversation(b.dataset.conversation));
  $('ai-new').onclick = () => { if (assistantBusy) return; assistantConversation = null; $('ai-messages').replaceChildren(); $('ai-actions').replaceChildren(); };
  $('ai-delete').onclick = async () => {
    if (assistantBusy) return;
    if (assistantConversation && confirm('Excluir esta conversa e suas ações pendentes?')) {
      await send('/assistant/conversations/' + assistantConversation, 'DELETE'); assistantConversation = null; viewAssistente();
    }
  };
  $('ai-form').onsubmit = async event => {
    event.preventDefault(); if (assistantBusy) return;
    const form = event.target, text = form.message.value.trim();
    if (!text) return;
    assistantBusy = true; form.querySelector('button').disabled = true; $('ai-state').textContent = 'Consultando seus dados…';
    try {
      const requestId = crypto.randomUUID();
      const data = await send('/assistant/messages', 'POST', {conversation_id: assistantConversation, request_id: requestId, message: text});
      assistantConversation = data.id;
      if ($('ai-form') !== form) return;
      form.message.value = ''; renderAssistantConversation(data);
      $('ai-state').textContent = data.request_status === 'failed'
        ? (assistantFailureMessages[data.failure_category] || assistantFailureMessages.request_failed)
        : 'Resposta salva.';
    } catch (error) { if ($('ai-form') === form) $('ai-state').textContent = errMsg(error, 'Falha de conexão. Confira o histórico antes de reenviar.'); }
    finally { assistantBusy = false; form.querySelector('button').disabled = false; }
  };
  if (assistantConversation) await openAssistantConversation(assistantConversation);
}
async function openAssistantConversation(id) {
  if (assistantBusy) return;
  assistantConversation = id;
  const container = $('ai-messages');
  try { const data = await api('/assistant/conversations/' + id); if (assistantConversation === id && $('ai-messages') === container && container) renderAssistantConversation(data); }
  catch (error) { if ($('ai-state')) $('ai-state').textContent = errMsg(error, 'Não foi possível carregar a conversa.'); }
}
function renderAssistantConversation(data) {
  $('ai-messages').innerHTML = data.messages.map(m => `<article class="ai-message"><small>${m.role === 'user' ? 'Você' : 'Assistente LeadCob'}</small><p>${esc(m.text).replace(/#\/(empresa|cobranca)\/(\d+)/g, '<a href="#/$1/$2">Abrir registro $2</a>')}</p></article>`).join('');
  $('ai-actions').innerHTML = data.actions.map(a => `<article class="warnbox"><b>Tarefa proposta · ${esc(a.status)}</b><p>${esc(a.payload.title)} · Empresa ${esc(a.payload.company_id)} · ${esc(a.payload.due_at || 'sem prazo')}</p>${a.status === 'pending' ? `<button data-approve="${esc(a.id)}">Confirmar criação</button> <button data-reject="${esc(a.id)}">Recusar</button>` : ''}</article>`).join('');
  document.querySelectorAll('[data-approve]').forEach(b => b.onclick = async () => { b.disabled = true; try { await send('/assistant/actions/' + b.dataset.approve + '/confirm', 'POST'); await openAssistantConversation(data.id); } catch (e) { toast(errMsg(e), 7000, true); b.disabled = false; } });
  document.querySelectorAll('[data-reject]').forEach(b => b.onclick = async () => { await send('/assistant/actions/' + b.dataset.reject + '/reject', 'POST'); await openAssistantConversation(data.id); });
}
