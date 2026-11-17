'use strict';
const $=id=>document.getElementById(id);
const base='/api/owner/commercial/organizations';
let csrf='',offset=0,busy=false;
const limit=50;
const roles={admin:'Administrador',member:'Operador',viewer:'Consulta'};
function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function notice(text){$('notice').textContent=text;}
async function api(path,method='GET',payload){
 const headers={};if(method!=='GET')headers['X-CSRF-Token']=csrf;
 if(payload!==undefined)headers['Content-Type']='application/json';
 const r=await fetch(path,{method,headers,body:payload===undefined?undefined:JSON.stringify(payload),credentials:'same-origin',cache:'no-store'});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Operação recusada ('+r.status+').');
 return data;
}
async function run(fn){if(busy)return;busy=true;notice('Processando…');try{await fn();notice('Operação concluída.');}catch(e){notice(e.message);}finally{busy=false;}}
function btn(text,fn){const b=el('button',text);b.type='button';b.className='secondary';b.addEventListener('click',()=>run(fn));return b;}
function memberForm(oid,reload){
 const f=el('form');
 for(const [name,label,type] of [['email','E-mail','email'],['password','Senha inicial','password']]){
  const l=el('label',label),i=el('input');i.name=name;i.type=type;i.required=true;i.maxLength=name==='email'?254:1024;if(name==='password'){i.minLength=14;i.autocomplete='new-password';}l.append(i);f.append(l);
 }
 const l=el('label','Permissão'),s=el('select');s.name='role';
 for(const [k,v] of Object.entries(roles)){const o=el('option',v);o.value=k;s.append(o);}s.value='member';l.append(s);f.append(l,el('button','Adicionar usuário'));
 f.addEventListener('submit',e=>{e.preventDefault();run(async()=>{try{await api(base+'/'+oid+'/members','POST',Object.fromEntries(new FormData(f)));}finally{f.elements.password.value='';}await reload();});});return f;
}
async function showMembers(org,area){let start=0;async function load(){
 const rows=await api(base+'/'+org.id+'/members?limit='+limit+'&offset='+start);
 area.replaceChildren(el('h3','Usuários da organização'));
 for(const u of rows){const r=el('p',u.email+' · '+(roles[u.role]||u.role)+' · '+(u.active?'Ativo':'Inativo'));area.append(r);}
 if(!rows.length)area.append(el('p','Nenhum usuário nesta página.'));
 const prev=btn('Usuários anteriores',async()=>{start-=limit;await load();}),next=btn('Mais usuários',async()=>{start+=limit;await load();});
 prev.disabled=start===0;next.disabled=rows.length<limit;area.append(prev,next,memberForm(org.id,async()=>{start=0;await load();}));
 }await load();}
async function load(){
 const rows=await api(base+'?limit='+limit+'&offset='+offset);
 $('rows').replaceChildren();for(const org of rows){
 const r=el('article');r.className='record';r.append(el('strong',org.name),el('p','Código: '+org.id+' · '+org.slug+' · '+(org.active?'Ativa':'Suspensa')));
 const actions=el('div');actions.className='actions';const details=el('div');
 actions.append(btn('Financeiro',()=>showFinance(org,details)),btn('Gerenciar assinatura',()=>showSubscription(org,details)),btn('Gerenciar usuários',()=>showMembers(org,details)),btn(org.active?'Suspender':'Reativar',async()=>{
 if(!confirm(org.active?'Suspender e encerrar todas as sessões desta organização?':'Reativar esta organização?'))return;
 await api(base+'/'+org.id,'PATCH',{active:!org.active});await load();
 }));r.append(actions,details);$('rows').append(r);}
 if(!rows.length)$('rows').append(el('p','Nenhuma organização nesta página.'));
 $('prev').disabled=offset===0;$('next').disabled=rows.length<limit;$('page').textContent='Página '+(offset/limit+1);
}
$('provision').addEventListener('submit',e=>{e.preventDefault();run(async()=>{let data;try{data=await api(base,'POST',Object.fromEntries(new FormData(e.target)));}finally{e.target.elements.password.value='';}e.target.reset();offset=0;await load();alert('Organização criada. Código de acesso: '+data.id);});});
$('refresh').addEventListener('click',()=>run(load));$('prev').addEventListener('click',()=>run(async()=>{offset=Math.max(0,offset-limit);await load();}));$('next').addEventListener('click',()=>run(async()=>{offset+=limit;await load();}));
run(async()=>{const s=await api('/api/auth/session');if(!s.authenticated||s.mode!=='cloud'||!s.csrf_token)throw Error('Entre no painel principal com a conta do proprietário.');csrf=s.csrf_token;await load();$('directory').hidden=false;$('admin-content').hidden=false;$('plans').hidden=false;$('release-diagnostics').hidden=false;await loadPlans();});

const planBase='/api/owner/commercial/plans';
const quotaLabels={members:'Usuários',leads:'Leads',contacts:'Contatos',tasks:'Tarefas',portfolios:'Carteiras',titles:'Títulos'};
const subscriptionLabels={unassigned:'Sem assinatura',scheduled:'Agendada',active:'Ativa',expired:'Vencida',cancelled:'Cancelada'};
let planOffset=0;
function money(cents){return (cents/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});}
function planDescription(plan){return Object.entries(quotaLabels).map(([k,label])=>label+': '+plan['max_'+k].toLocaleString('pt-BR')).join(' · ');}
async function loadPlans(){
 const rows=await api(planBase+'?limit='+limit+'&offset='+planOffset);
 $('plan-rows').replaceChildren();
 for(const p of rows){const r=el('article');r.className='record';r.append(el('strong',p.name+' · '+money(p.monthly_price_cents)+'/mês'),el('p',p.code+' · '+(p.active?'Ativo':'Inativo')),el('p',planDescription(p)),btn(p.active?'Desativar plano':'Ativar plano',async()=>{if(!confirm('Confirmar alteração de disponibilidade do plano '+p.name+'?'))return;await api(planBase+'/'+p.id,'PATCH',{active:!p.active});await loadPlans();}));$('plan-rows').append(r);}
 if(!rows.length)$('plan-rows').append(el('p','Nenhum plano nesta página.'));
 $('plan-prev').disabled=planOffset===0;$('plan-next').disabled=rows.length<limit;$('plan-page').textContent='Página '+(planOffset/limit+1);
}
$('create-plan').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const f=e.target,v=Object.fromEntries(new FormData(f));if(!/^\d+(\.\d{1,2})?$/.test(v.price))throw Error('Informe uma mensalidade com até duas casas decimais.');const [reais,centavos='']=v.price.split('.');v.monthly_price_cents=Number(reais)*100+Number(centavos.padEnd(2,'0'));delete v.price;for(const k of Object.keys(quotaLabels))v['max_'+k]=Number(v['max_'+k]);await api(planBase,'POST',v);f.reset();planOffset=0;await loadPlans();});});
$('refresh-plans').addEventListener('click',()=>run(loadPlans));$('plan-prev').addEventListener('click',()=>run(async()=>{planOffset=Math.max(0,planOffset-limit);await loadPlans();}));$('plan-next').addEventListener('click',()=>run(async()=>{planOffset+=limit;await loadPlans();}));
function dateText(value){return value?new Date(value).toLocaleString('pt-BR',{timeZone:'America/Manaus'}):'—';}
function localDateValue(value){if(!value)return '';const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Manaus',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));const d=Object.fromEntries(parts.map(p=>[p.type,p.value]));return d.year+'-'+d.month+'-'+d.day+'T'+d.hour+':'+d.minute;}
async function showSubscription(org,area){
 const path=base+'/'+org.id+'/subscription';
 const sub=await api(path);
 area.replaceChildren(el('h3','Assinatura de '+org.name),el('p','Situação: '+(subscriptionLabels[sub.status]||sub.status)));
 if(sub.plan)area.append(el('p',sub.plan.name+' · '+money(sub.plan.monthly_price_cents)+'/mês'),el('p','Vigência (Manaus): '+dateText(sub.starts_at)+' a '+dateText(sub.ends_at)),el('p',planDescription(sub.plan)));
 area.append(el('p','Atribuição administrativa não confirma recebimento de pagamento.'));
 const form=el('form'),label=el('label','Código numérico do plano ativo'),input=el('input');input.name='plan_id';input.type='number';input.min='1';input.required=true;if(sub.plan)input.value=sub.plan.id;label.append(input);form.append(label);
 const plans=await api(planBase+'?limit=250&offset=0');
 const active=plans.filter(p=>p.active);
 if(active.length){const hint=el('p','Planos ativos nesta consulta: '+active.map(p=>p.id+' — '+p.name+' ('+money(p.monthly_price_cents)+')').join(' · '));form.append(hint);}
 else form.append(el('p','Nenhum plano ativo na primeira página. Ative um plano no catálogo antes de atribuir.'));
 for(const [name,title,value] of [['starts_at','Início (horário de Manaus)',sub.starts_at],['ends_at','Fim (horário de Manaus)',sub.ends_at]]){const l=el('label',title),i=el('input');i.type='datetime-local';i.name=name;i.required=true;i.value=localDateValue(value);l.append(i);form.append(l);}
 form.append(el('button','Salvar vigência'));
 form.addEventListener('submit',e=>{e.preventDefault();run(async()=>{const v=Object.fromEntries(new FormData(form));v.plan_id=Number(v.plan_id);v.starts_at=new Date(v.starts_at+'-04:00').toISOString();v.ends_at=new Date(v.ends_at+'-04:00').toISOString();if(!confirm('Confirmar atribuição ou renovação da assinatura?'))return;await api(path,'PUT',v);await showSubscription(org,area);});});
 area.append(form);
 if(sub.plan&&sub.status!=='cancelled')area.append(btn('Cancelar assinatura',async()=>{if(!confirm('Cancelar a assinatura desta organização? Os dados serão preservados.'))return;await api(path+'/cancel','POST');await showSubscription(org,area);}));
}


// Owner-only financial operations; all amounts and statuses originate from the API.
const ledgerLabels={open:'Em aberto',paid:'Baixado',void:'Cancelado'};
const outcomeLabels={sandbox_received:'Recebido em teste',not_received:'Não recebido',divergence:'Divergência',refund_review:'Revisar estorno',chargeback_review:'Revisar chargeback',deleted_review:'Revisar exclusão',financial_review:'Revisão financeira'};
async function showFinance(org,area){
 const root=base+'/'+org.id, path=root+'/invoices';
 let pageOffset=0;
 async function loadFinance(){
  const rows=await api(path+'?limit='+limit+'&offset='+pageOffset);
  area.replaceChildren(el('h3','Financeiro · '+org.name),el('p','Recebíveis internos em BRL. Sandbox não comprova pagamento real nem libera assinatura.'));
  area.append(btn('Processar eventos sandbox',async()=>{
   const result=await api(root+'/asaas-sandbox/process-pending?limit=5','POST');
   const report=el('div');report.append(el('p','Selecionados: '+result.selected+' · Tentativas: '+result.attempted));
   for(const x of result.results)report.append(el('p',x.event_id+' · '+(outcomeLabels[x.outcome]||x.status)));
   if(!result.results.length)report.append(el('p','Nenhum evento vinculado pendente.'));
   area.append(report);
  }));
  const form=el('form');
  for(const [name,label,type] of [['plan_id','Código do plano ativo','number'],['period_start','Início do período','date'],['period_end','Fim do período','date'],['due_date','Vencimento','date']]){
   const l=el('label',label),i=el('input');i.name=name;i.type=type;i.required=true;if(type==='number')i.min='1';l.append(i);form.append(l);
  }
  form.append(el('button','Registrar recebível'));
  form.addEventListener('submit',e=>{e.preventDefault();run(async()=>{const v=Object.fromEntries(new FormData(form));v.plan_id=Number(v.plan_id);await api(path,'POST',v);pageOffset=0;await loadFinance();});});
  area.append(form);
  if(!rows.length)area.append(el('p','Nenhum recebível nesta página.'));
  for(const row of rows){
   const card=el('article');card.className='record';
   const invoicePath=path+'/'+row.id, detail=el('div');
   card.append(el('strong','#'+row.id+' · '+money(row.amount_cents)),el('p',(ledgerLabels[row.status]||row.status)+' · '+row.period_start+' a '+row.period_end+' · Vencimento: '+row.due_date));
   if(row.status==='open'){
    card.append(btn('Registrar baixa real',async()=>{
     const reference=prompt('Referência do comprovante bancário real (não utilize pagamentos sandbox):');
     if(reference===null)return;
     if(!reference.trim()||!confirm('Confirme que o valor integral '+money(row.amount_cents)+' foi recebido e conferido no banco.'))return;
     const paidAt=prompt('Data e hora real do pagamento (ISO 8601 com fuso, ex.: 2026-11-17T10:00:00-04:00):');
     if(paidAt===null)return;
     if(!Number.isFinite(Date.parse(paidAt))||!/(Z|[+-][0-9]{2}:[0-9]{2})$/.test(paidAt))throw Error('Informe data válida com fuso horário.');
     await api(invoicePath+'/settle','POST',{amount_cents:row.amount_cents,payment_reference:reference.trim(),paid_at:new Date(paidAt).toISOString()});await loadFinance();
    }),btn('Cancelar recebível',async()=>{if(!confirm('Cancelar o recebível #'+row.id+'? Isso não cancela cobranças no Asaas.'))return;await api(invoicePath+'/void','POST');await loadFinance();}));
   }
   if(row.status==='paid')card.append(btn('Renovar assinatura',async()=>{if(!confirm('Aplicar este recebível à vigência contratual?'))return;const result=await api(invoicePath+'/renew','POST');await loadFinance();area.append(el('p',result.replayed?'Renovação já registrada.':'Renovação registrada.'));}));
   card.append(btn('Consultar eventos sandbox',async()=>{
    const result=await api(invoicePath+'/asaas-sandbox/events?limit=50&offset=0');
    detail.replaceChildren(el('h4','Eventos sandbox (até 50 mais recentes)'));
    for(const event of result.events)detail.append(el('p',event.event_type+' · '+(outcomeLabels[event.outcome]||'Pendente de observação')+' · '+event.event_id));
    if(!result.events.length)detail.append(el('p','Nenhum evento vinculado.'));
   }),detail);
   area.append(card);
  }
  const prev=btn('Anterior',async()=>{pageOffset=Math.max(0,pageOffset-limit);await loadFinance();}),next=btn('Próxima',async()=>{pageOffset+=limit;await loadFinance();});
  prev.disabled=pageOffset===0;next.disabled=rows.length<limit;area.append(prev,el('span',' Página '+(pageOffset/limit+1)+' '),next);
  area.append(btn('Histórico de renovações',async()=>{
   const records=await api(root+'/renewals?limit=50&offset=0'), history=el('div');
   history.append(el('h4','Últimas 50 renovações'));
   for(const x of records)history.append(el('p','Recebível #'+x.invoice_id+' · '+x.previous_end+' → '+x.new_end));
   if(!records.length)history.append(el('p','Nenhuma renovação registrada.'));
   area.append(history);
  }));
 }
 await loadFinance();
}


const readinessLabels={production_mode:'Ambiente de produção',postgresql:'Banco PostgreSQL',https_origin:'Origem HTTPS',owner_auth_configured:'Autenticação do proprietário configurada',commercial_auth_enabled:'Autenticação comercial ativa',entitlements_enabled:'Cotas e vigência ativas',demo_disabled:'Demonstração desativada',schema_tables_present:'Tabelas esperadas presentes',expected_active_catalog:'Catálogo ativo com preços esperados'};
const manualGateLabels={postgresql_concurrency:'Concorrência PostgreSQL — validar cenários de aceite',browser_e2e:'Fluxos completos de navegador',sandbox_provider_homologation:'Homologação externa Asaas',backup_restore_drill:'Ensaio de backup e restauração',privacy_and_terms_review:'Revisão de privacidade e termos',production_payment_integration:'Integração de pagamentos em produção'};
async function loadReadiness(){
 const area=$('readiness-results');
 area.replaceChildren(el('p','Verificando ambiente…'));
 try{
  const x=await api('/api/owner/commercial/readiness');
  area.replaceChildren(el('strong',x.configuration_checks_passed?'Configuração verificada — aceite manual necessário':'Configuração com pendências'));
  for(const [key,value] of Object.entries(x.configuration_checks))area.append(el('p',(readinessLabels[key]||key)+': '+(value===true?'Verificado':'Pendente')));
  if(x.missing_tables.length)area.append(el('p','Tabelas ausentes: '+x.missing_tables.join(', ')));
  area.append(el('h3','Catálogo observado'));
  for(const p of x.plans)area.append(el('p',p.code+' · '+money(p.amount_cents)+' · '+(p.active?'Ativo':'Inativo')));
  if(!x.plans.length)area.append(el('p','Nenhum plano cadastrado.'));
  area.append(el('h3','Sandbox'),el('p','Chave configurada: '+(x.sandbox.api_configured?'Sim':'Não')+' · Token configurado: '+(x.sandbox.webhook_token_configured?'Sim':'Não')+'. Configuração não comprova conexão.'));
  area.append(el('h3','Aceite manual obrigatório'));
  for(const key of x.manual_gates)area.append(el('p',manualGateLabels[key]||key));
  area.append(el('p','Lançamento não certificado. Nenhuma configuração foi alterada.'));
 }catch(e){area.replaceChildren(el('p',e.message));throw e;}
}
$('refresh-readiness').addEventListener('click',()=>run(loadReadiness));
