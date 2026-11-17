'use strict';
const $=id=>document.getElementById(id),base='/api/contacts/discovery-jobs',size=50;
let csrf='',offset=0,itemOffset=0,job=null,busy=false;
const labels={queued:'Na fila',running:'Processando',completed:'Concluído',failed:'Falhou',skipped:'Ignorado'};
const reasons={completed:'Pesquisa concluída',suppressed:'Empresa suprimida',not_found:'Empresa não encontrada',missing_website:'Sem site cadastrado',invalid_cnpj:'CNPJ inválido',changed_or_suppressed:'Cadastro alterado ou suprimido',unavailable:'Site indisponível',error:'Falha de processamento',lease_expired:'Execução interrompida'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function notice(text){$('notice').textContent=text;}
async function api(path,method='GET',payload){
 const headers={};if(payload!==undefined){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrf;}
 const r=await fetch(path,{method,headers,credentials:'same-origin',cache:'no-store',body:payload===undefined?undefined:JSON.stringify(payload)});
 const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Operação recusada ('+r.status+').');return data;
}
async function run(fn){if(busy)return;busy=true;notice('Carregando…');try{await fn();notice('Dados atualizados.');}catch(e){notice(e.message);}finally{busy=false;}}
function btn(text,fn){const b=el('button',text,'secondary');b.type='button';b.addEventListener('click',()=>run(fn));return b;}
function finished(r){return r.completed+r.failed+r.skipped;}
async function history(){
 const rows=await api(base+'?limit='+size+'&offset='+offset);
 $('history').replaceChildren();
 for(const r of rows){const card=el('article',undefined,'record');card.append(el('strong','Lote #'+r.job_id),el('p','Criado: '+new Date(r.created_at.endsWith('Z')||/[+-]\d\d:\d\d$/.test(r.created_at)?r.created_at:r.created_at+'Z').toLocaleString('pt-BR')),el('p',finished(r)+' de '+r.total+' finalizados · '+r.failed+' falhas'),btn('Consultar lote',async()=>{job=r.job_id;itemOffset=0;await detail();}));$('history').append(card);}
 if(!rows.length)$('history').append(el('p','Nenhum lote nesta página.'));
 $('prev').disabled=offset===0;$('next').disabled=rows.length<size;$('page').textContent='Página '+(offset/size+1);
}
async function detail(){
 if(job===null)return;
 const [r,items]=await Promise.all([api(base+'/'+job),api(base+'/'+job+'/items?limit='+size+'&offset='+itemOffset)]);
 $('detail-title').textContent='Lote #'+job;$('metrics').replaceChildren();
 for(const [key,label] of Object.entries(labels)){const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',String(r[key])));$('metrics').append(card);}
 $('progress').max=Math.max(r.total,1);$('progress').value=finished(r);$('summary').textContent=finished(r)+' de '+r.total+' registros finalizados. Concluído não significa contato verificado.';
 $('items').replaceChildren();for(const x of items){const card=el('article',undefined,'record');card.append(el('strong','Empresa #'+x.company_id),el('p',(labels[x.status]||x.status)+' · '+x.attempts+' tentativa(s)'));if(x.result?.status)card.append(el('p',reasons[x.result.status]||x.result.status));if(Number.isInteger(x.result?.added))card.append(el('p','Contatos adicionados nesta tentativa: '+x.result.added));if(Number.isInteger(x.result?.pages_read))card.append(el('p','Páginas lidas: '+x.result.pages_read));$('items').append(card);}
 if(!items.length)$('items').append(el('p','Nenhum registro nesta página.'));
 $('item-prev').disabled=itemOffset===0;$('item-next').disabled=items.length<size;$('item-page').textContent='Página '+(itemOffset/size+1);$('detail').hidden=false;
}
$('create').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const raw=new FormData(e.target).get('ids').trim().split(/[\s,;]+/);if(!raw.every(x=>/^\d+$/.test(x)&&Number.isSafeInteger(Number(x))&&Number(x)>0))throw Error('Informe somente IDs inteiros positivos.');const ids=[...new Set(raw.map(Number))];if(ids.length>1000)throw Error('Limite de 1.000 empresas por lote.');const r=await api(base,'POST',{company_ids:ids});e.target.reset();job=r.job_id;offset=itemOffset=0;await history();await detail();});});
$('refresh').addEventListener('click',()=>run(history));$('refresh-detail').addEventListener('click',()=>run(detail));
$('prev').addEventListener('click',()=>run(async()=>{offset=Math.max(0,offset-size);await history();}));
$('next').addEventListener('click',()=>run(async()=>{offset+=size;await history();}));
$('item-prev').addEventListener('click',()=>run(async()=>{itemOffset=Math.max(0,itemOffset-size);await detail();}));
$('item-next').addEventListener('click',()=>run(async()=>{itemOffset+=size;await detail();}));
run(async()=>{const s=await api('/api/auth/session');if(!s.authenticated||s.mode!=='cloud'||!s.csrf_token)throw Error('Sessão do proprietário obrigatória.');csrf=s.csrf_token;await history();$('content').hidden=false;await coverage();});


const channelNames={email:'E-mail',phone:'Telefone',whatsapp:'WhatsApp',linkedin:'LinkedIn',instagram:'Instagram',facebook:'Facebook',website:'Site'};
async function coverage(){
 const qs=new URLSearchParams(new FormData($('coverage-form')));
 const root=$('coverage');root.replaceChildren(el('p','Consultando diretório…'));
 try{
 const r=await api('/api/contacts/coverage?'+qs);
 const grid=el('div',undefined,'metrics');
 for(const [label,value] of [['Empresas elegíveis',r.eligible_company_records],['Com canal cadastrado',r.with_any_channel],['Sem canal cadastrado',r.without_registered_channel],['Com canal verificado',r.with_any_verified_channel]]){
 const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',Number(value).toLocaleString('pt-BR')));grid.append(card);}
 root.replaceChildren(grid);
 for(const [kind,label] of Object.entries(channelNames)){
 const c=r.channels[kind],row=el('article',undefined,'record');
 const pct=r.eligible_company_records?100*c.available/r.eligible_company_records:0;
 row.append(el('strong',label),el('p',c.available.toLocaleString('pt-BR')+' empresas · '+pct.toFixed(1).replace('.',',')+'% da base · '+c.verified.toLocaleString('pt-BR')+' verificadas'));
 const bar=el('progress');bar.max=Math.max(r.eligible_company_records,1);bar.value=c.available;bar.setAttribute('aria-label',label+' — cobertura');row.append(bar);root.append(row);}
 }catch(e){root.replaceChildren(el('p','Cobertura indisponível: '+e.message));throw e;}
}
$('coverage-form').addEventListener('submit',e=>{e.preventDefault();run(coverage);});
