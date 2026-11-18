'use strict';
const $=id=>document.getElementById(id);
let session=null, moduleName='leads', offset=0, epoch=0, busy=false;
const size=50;
const stages={identified:'Identificado',contacted:'Contatado',negotiation:'Negociação',won:'Ganho',lost:'Perdido'};
const names={prospects:'Pesquisa cadastral',leads:'CRM',tasks:'Agenda',portfolios:'Carteiras financeiras',contacts:'Contatos institucionais',settings:'Configurações',assistant:'Inteligência da organização',subscription:'Meu plano'};
const channels={email:'E-mail',phone:'Telefone',whatsapp:'WhatsApp',website:'Site',linkedin:'LinkedIn',instagram:'Instagram',facebook:'Facebook'};
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function status(message){$('notice').textContent=message;}
async function api(path,method='GET',body){
 const headers={};if(body!==undefined)headers['Content-Type']='application/json';
 if(session&&method!=='GET')headers['X-CSRF-Token']=session.csrf_token;
 const r=await fetch('/api/commercial/'+path,{method,headers,credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Não foi possível concluir a operação ('+r.status+').');
 return data;
}
function workspace(path,method='GET',body){return api('workspace/'+session.organization_id+'/'+path,method,body);}
function clear(){epoch++;session=null;$('workspace').hidden=true;$('login').hidden=false;$('form-area').replaceChildren();$('results').replaceChildren();$('identity').textContent='Área comercial privada';}
async function enter(data){session=data;$('login').hidden=true;$('workspace').hidden=false;$('identity').textContent='Organização '+data.organization_id+' · '+data.role;offset=0;await load();}
async function action(fn){if(busy)return;busy=true;status('Processando…');try{await fn();status('Operação concluída.');}catch(e){status(e.message);}finally{busy=false;}}
$('login-form').addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);action(async()=>{const data=await api('auth/login','POST',{organization_id:Number(f.get('organization_id')),email:f.get('email'),password:f.get('password')});e.target.reset();await enter(data);});});
$('logout').addEventListener('click',()=>action(async()=>{await api('auth/logout','POST',{organization_id:session.organization_id});clear();}));
function canWrite(){return session.role!=='viewer';}
function button(text,fn){const b=el('button',text,'secondary');b.type='button';b.addEventListener('click',()=>action(fn));return b;}
function field(name,label,kind='text',value='',options=null){return {name,label,kind,value,options};}
function form(fields,label,submit){const f=el('form');for(const d of fields){const l=el('label',d.label);let i;
 if(d.options){i=el('select');for(const [value,title] of Object.entries(d.options)){const o=el('option',title);o.value=value;i.append(o);}}
 else{i=el(d.kind==='textarea'?'textarea':'input');if(d.kind!=='textarea')i.type=d.kind;}
 i.name=d.name;i.required=d.name!=='notes';if(d.kind==='checkbox'){i.checked=Boolean(d.value);}else{i.value=d.value;}
 l.append(i);f.append(l);}
 const b=el('button',label);f.append(b);
 f.addEventListener('submit',e=>{e.preventDefault();const payload=Object.fromEntries(new FormData(f));action(()=>submit(payload));});return f;}
function record(heading,lines){const r=el('article',undefined,'record');r.append(el('strong',heading));for(const line of lines)r.append(el('p',line));return r;}
function today(){const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');}
function leadFields(x={}){return [field('name','Empresa','text',x.name||''),field('notes','Observações','textarea',x.notes||''),field('stage','Etapa','text',x.stage||'identified',stages)];}
function taskFields(){return [field('title','Tarefa'),field('due_date','Vencimento','date',today())];}
function contactFields(){return [field('cnpj','CNPJ'),field('kind','Canal','text','email',channels),field('value','Contato'),field('source_url','URL de origem','url'),field('institutional','Confirmo que é um canal institucional','checkbox')];}
function createForm(fields,label,path,transform=x=>x){$('form-area').append(form(fields,label,async x=>{await workspace(path,'POST',transform(x));await load();}));}
function showLead(x){const r=record(x.name,[stages[x.stage]||x.stage,x.notes]);if(canWrite()){const a=el('div',undefined,'actions');a.append(button('Editar',async()=>{$('form-area').replaceChildren(form(leadFields(x),'Salvar alterações',async v=>{await workspace('leads/'+x.id,'PUT',v);await load();}));$('form-area').querySelector('input').focus();}),button('Excluir',async()=>{if(confirm('Excluir este lead?')){await workspace('leads/'+x.id,'DELETE');await load();}}));r.append(a);}return r;}
function showTask(x){const r=record(x.title,['Vencimento: '+x.due_date,x.completed_at?'Concluída':'Pendente']);if(canWrite()){const a=el('div',undefined,'actions');a.append(button(x.completed_at?'Reabrir':'Concluir',async()=>{await workspace('tasks/'+x.id,'PATCH',{completed:!x.completed_at});await load();}),button('Excluir',async()=>{if(confirm('Excluir esta tarefa?')){await workspace('tasks/'+x.id,'DELETE');await load();}}));r.append(a);}return r;}
async function openPortfolio(x,container,version){const root='portfolios/'+x.id;if(version!==epoch)return;container.replaceChildren(el('p','Carregando títulos…'));let titleOffset=0;
 async function draw(){const [summary,titles]=await Promise.all([workspace(root+'/summary?as_of='+today()),workspace(root+'/titles?limit='+size+'&offset='+titleOffset)]);if(version!==epoch)return;container.replaceChildren(record('Resumo em '+summary.as_of,['Total: R$ '+summary.total,'Pago: R$ '+summary.paid,'Vencido: R$ '+summary.overdue,'A vencer: R$ '+summary.current,'Em aberto: R$ '+summary.outstanding]));
 if(canWrite())container.append(form([field('reference','Referência'),field('amount','Valor em reais (ex.: 100.50)'),field('due_date','Vencimento','date',today())],'Adicionar título',async v=>{await workspace(root+'/titles','POST',v);titleOffset=0;await draw();}));
 for(const t of titles)container.append(record(t.reference,['R$ '+t.amount,'Vencimento: '+t.due_date,t.paid_date?'Pago em '+t.paid_date:'Em aberto']));
 if(!titles.length)container.append(el('p','Nenhum título nesta página.'));
 const controls=el('div',undefined,'actions');const prev=button('Títulos anteriores',async()=>{titleOffset-=size;await draw();});prev.disabled=titleOffset===0;const next=button('Mais títulos',async()=>{titleOffset+=size;await draw();});next.disabled=titles.length<size;controls.append(prev,next);container.append(controls);}
 await draw();}
function showPortfolio(x,version){const r=record(x.name,['Data-base: '+x.reference_date]);const details=el('div');r.append(button('Consultar títulos e saldo',()=>openPortfolio(x,details,version)),details);return r;}
function showContact(x){return record(channels[x.kind]||x.kind,[x.cnpj,x.value,'Origem: '+x.source_url,'Status: a verificar']);}
async function load(){if(!session)return;const version=++epoch;const current=moduleName;$('module-title').textContent=names[current];$('form-area').replaceChildren();$('results').replaceChildren(el('p','Carregando…'));$('pagination').hidden=true;
 for(const b of $('nav').querySelectorAll('button'))b.setAttribute('aria-current',String(b.dataset.module===current));
 try{
 if(current==='prospects'){
 const root=$('results');
 root.replaceChildren(el('p','Informe um CNPJ conhecido. Consulta pública individual; não pesquisa toda a cidade nem confirma demanda.'));
 $('form-area').append(form([field('cnpj','CNPJ')],'Consultar cadastro',async v=>{
 const key=v.cnpj.replace(/[^0-9A-Za-z]/g,'').toUpperCase();
 if(key.length!==14)throw Error('Informe um CNPJ válido.');
 root.replaceChildren(el('p','Consultando fonte cadastral…'));
 try{
 const x=await workspace('prospects/'+encodeURIComponent(key));if(version!==epoch)return;
 root.replaceChildren(record(x.razao_social,[x.cnpj,(x.municipio||'—')+' / '+(x.uf||'—'),'CNAE: '+(x.cnae_principal||'—'),'Situação: '+(x.situacao_cadastral||'—'),'Fonte: '+x.source,'Consulta: '+x.observed_at,x.note]));
 if(canWrite()&&x.situacao_cadastral==='ATIVA'){
 root.append(button('Adicionar ao CRM privado',async()=>{
 if(!confirm('Cadastrar esta empresa como lead identificado, sem demanda confirmada?'))return;
 await workspace('leads','POST',{name:x.razao_social.slice(0,220),stage:'identified',notes:'CNPJ '+x.cnpj+' · '+(x.municipio||'')+' / '+(x.uf||'')+' · Fonte '+x.source+' · Consulta '+x.observed_at+' · Cadastro, não demanda confirmada.'});
 moduleName='leads';offset=0;await load();
 }));
 }
 }catch(e){if(version===epoch)root.replaceChildren(el('p',e.message));throw e;}
 }));
 return;
 }
 if(current==='assistant'){
 const x=await workspace('assistant/context');if(version!==epoch)return;
 const root=$('results');
 root.replaceChildren(record('Resumo da sua organização',['Leads: '+x.lead_count,'Tarefas pendentes: '+x.pending_tasks,'Carteiras: '+x.portfolio_count]),record('Funil comercial',Object.entries(stages).map(([key,label])=>label+': '+(x.lead_stages[key]||0))),record('Empresas com canais cadastrados',Object.entries(channels).map(([key,label])=>label+': '+(x.companies_by_channel[key]||0))),el('p',x.note));
 const history=await workspace('assistant/history');if(version!==epoch)return;
 const panel=el('section');panel.append(el('h3','Meu histórico privado'));
 for(const item of history)panel.append(record(item.prompt,[item.answer||('Estado: '+item.status)]));
 if(!history.length)panel.append(el('p','Nenhuma solicitação registrada.'));
 root.append(panel);
 if(x.generation_enabled&&canWrite())$('form-area').append(form([field('prompt','Pergunta (não inclua dados pessoais ou confidenciais)','textarea')],'Enviar à IA',async v=>{
 if(!v.prompt.trim()||v.prompt.length>2000)throw Error('Informe até 2.000 caracteres.');
 if(!confirm('Enviar sua pergunta e os indicadores agregados da organização ao provedor de IA?'))return;
 const response=await workspace('assistant/generate','POST',{request_id:crypto.randomUUID(),prompt:v.prompt});
 await load();if(response.status!=='completed')throw Error('Não foi possível gerar a resposta. Consulte o histórico antes de reenviar.');
 }));
 return;
 }
 if(current==='subscription'){const x=await workspace('subscription');if(version!==epoch)return;showSubscription(x);return;}
 if(current==='settings'){const x=await workspace('settings');if(version!==epoch)return;$('results').replaceChildren(record('Preferências atuais',['Fuso: '+x.timezone,'Follow-up: '+x.followup_days.join(', ')+' dias','Registros por página: '+x.default_page_size]));
 if(session.role==='admin')$('form-area').append(form([field('timezone_name','Fuso horário','text',x.timezone),field('followup_days','Dias separados por vírgulas','text',x.followup_days.join(',')),field('default_page_size','Registros por página','number',x.default_page_size)],'Salvar preferências',async v=>{await workspace('settings','PUT',{timezone_name:v.timezone_name,followup_days:v.followup_days.split(',').map(Number),default_page_size:Number(v.default_page_size)});await load();}));return;}
 const rows=await workspace(current+'?limit='+size+'&offset='+offset);if(version!==epoch)return;
 if(canWrite()){
 if(current==='leads')createForm(leadFields(),'Adicionar lead','leads');
 if(current==='tasks')createForm(taskFields(),'Adicionar tarefa','tasks');
 if(current==='portfolios')createForm([field('name','Nome da carteira'),field('reference_date','Data-base','date',today())],'Criar carteira','portfolios');
 if(current==='contacts'){createForm(contactFields(),'Cadastrar contato','contacts',v=>({...v,institutional:v.institutional==='on'}));$('form-area').append(form([field('cnpj','CNPJ a suprimir'),field('reason','Motivo')],'Não contatar',async v=>{await workspace('suppressions','POST',v);await load();}));}}
 const renderer={leads:showLead,tasks:showTask,portfolios:x=>showPortfolio(x,version),contacts:showContact}[current];
 $('results').replaceChildren(...rows.map(renderer));if(!rows.length)$('results').append(el('p','Nenhum registro nesta página.'));
 $('pagination').hidden=false;$('prev').disabled=offset===0;$('next').disabled=rows.length<size;$('page').textContent='Página '+(offset/size+1);
 }catch(e){if(version===epoch){$('results').replaceChildren(el('p',e.message));status(e.message);if(busy)throw e;}}}
$('nav').addEventListener('click',e=>{const b=e.target.closest('button[data-module]');if(b&&!busy){moduleName=b.dataset.module;offset=0;load();}});
$('prev').addEventListener('click',()=>{if(offset>=size&&!busy){offset-=size;load();}});
$('next').addEventListener('click',()=>{if(!busy){offset+=size;load();}});

function showSubscription(x){
 const labels={unassigned:'Sem assinatura',scheduled:'Agendada',active:'Ativa',expired:'Vencida',cancelled:'Cancelada'};
 const root=$('results');
 root.replaceChildren(record('Situação da assinatura',[labels[x.status]||x.status]));
 if(!x.plan){root.append(el('p','Consulte o administrador para contratar um plano.'));return;}
 const p=x.plan,fmt=v=>new Date(v).toLocaleString('pt-BR',{timeZone:'America/Manaus'});
 root.append(record(p.name,[(p.monthly_price_cents/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})+' por mês','Início: '+fmt(x.starts_at),'Fim: '+fmt(x.ends_at),'Vigência em horário de Manaus. Não representa comprovante de pagamento.']));
 if(x.enforcement_enabled===false)root.append(el('p','A aplicação automática dos limites está desativada neste ambiente.'));
 if(x.enforcement_enabled===true&&x.status!=='active')root.append(el('p','Novas gravações estão bloqueadas. Seus dados continuam disponíveis para consulta.'));
 const quotas={members:'Usuários',leads:'Leads',contacts:'Contatos',tasks:'Tarefas',portfolios:'Carteiras',titles:'Títulos'};
 for(const [key,label] of Object.entries(quotas)){
 const max=p['max_'+key],used=x.usage?.[key],r=record(label,[Number.isInteger(used)?used.toLocaleString('pt-BR')+' de '+max.toLocaleString('pt-BR')+' utilizados':'Limite contratado: '+max.toLocaleString('pt-BR')+' · consumo ainda indisponível']);
 if(Number.isInteger(used)){const bar=el('progress');bar.max=Math.max(max,1);bar.value=Math.min(used,bar.max);bar.setAttribute('aria-label',label+' utilizados');r.append(bar);if(used>=max)r.append(el('p','Limite atingido ou excedido.'));}root.append(r);}
}
