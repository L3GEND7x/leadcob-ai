'use strict';
const $=id=>document.getElementById(id),base='/api/contacts/discovery-jobs',size=50;
let csrf='',offset=0,itemOffset=0,job=null,busy=false;
const labels={queued:'Na fila',running:'Processando',completed:'Concluído',failed:'Falhou',skipped:'Ignorado'};
const reasons={completed:'Pesquisa concluída',suppressed:'Empresa suprimida',not_found:'Empresa não encontrada',missing_website:'Sem site cadastrado',invalid_cnpj:'CNPJ inválido',changed_or_suppressed:'Cadastro alterado ou suprimido',unavailable:'Site indisponível',error:'Falha de processamento',lease_expired:'Execução interrompida',invalid_claim_metadata:'Reserva inconsistente',attempts_exhausted:'Tentativas esgotadas'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function notice(text){$('notice').textContent=text;}
async function api(path,method='GET',payload){
 const headers={};if(payload!==undefined){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrf;}
 const r=await fetch(path,{method,headers,credentials:'same-origin',cache:'no-store',body:payload===undefined?undefined:JSON.stringify(payload)});
 const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Operação recusada ('+r.status+').');return data;
}
async function run(fn){if(busy)return;busy=true;notice('Carregando…');try{const message=await fn();notice(typeof message==='string'?message:'Dados atualizados.');}catch(e){notice(e.message);}finally{busy=false;}}
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
 $('process-one').disabled=!r.queued && !r.running;
 $('items').replaceChildren();for(const x of items){const card=el('article',undefined,'record');card.append(el('strong','Empresa #'+x.company_id),el('p',(labels[x.status]||x.status)+' · '+x.attempts+' tentativa(s)'));if(x.result?.status)card.append(el('p',reasons[x.result.status]||x.result.status));if(Number.isInteger(x.result?.added))card.append(el('p','Contatos adicionados nesta tentativa: '+x.result.added));if(Number.isInteger(x.result?.pages_read))card.append(el('p','Páginas lidas: '+x.result.pages_read));$('items').append(card);}
 if(!items.length)$('items').append(el('p','Nenhum registro nesta página.'));
 $('item-prev').disabled=itemOffset===0;$('item-next').disabled=items.length<size;$('item-page').textContent='Página '+(itemOffset/size+1);$('detail').hidden=false;
}
$('create').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const raw=new FormData(e.target).get('ids').trim().split(/[\s,;]+/);if(!raw.every(x=>/^\d+$/.test(x)&&Number.isSafeInteger(Number(x))&&Number(x)>0))throw Error('Informe somente IDs inteiros positivos.');const ids=[...new Set(raw.map(Number))];if(ids.length>1000)throw Error('Limite de 1.000 empresas por lote.');const r=await api(base,'POST',{company_ids:ids});e.target.reset();job=r.job_id;offset=itemOffset=0;await history();await detail();});});
$('process-one').addEventListener('click',()=>{if(job===null)return;
 if(!confirm('Pesquisar somente 1 empresa deste lote no site cadastrado? Confira previamente a titularidade do site. Nenhuma mensagem será enviada.'))return;
 run(async()=>{
  const result=await api(base+'/'+job+'/process-one','POST',{});
  await detail();await history();await coverage();await loadWorkerDiagnostics();
  return result.attempted?'Tentativa executada. Confira resultado e contatos antes de usar.':'Sem empresas elegíveis neste lote.';
 });
});
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

$('export-contacts').addEventListener('click',()=>run(async()=>{
 const status=$('export-status').value,offset=$('export-offset').value;
 if(status==='todos'&&!confirm('Incluir contatos A VERIFICAR, com fontes para revisão? Não envie mensagens sem validação prévia e base legal.'))return 'Exportação cancelada.';
 const params=new URLSearchParams(new FormData($('coverage-form')));
 if(!params.get('uf'))params.set('uf','AM');
 if(!params.get('city'))params.set('city','Manaus');
 params.set('status',status);params.set('limit','5000');params.set('offset',offset||'0');
 const response=await fetch('/api/contacts/export.csv?'+params,{credentials:'same-origin',cache:'no-store'});
 if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(typeof data.detail==='string'?data.detail:'Não foi possível exportar os contatos.');}
 const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download='leadcob-contatos-institucionais.csv';document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 return 'CSV gerado com '+Number(response.headers.get('X-Exported-Rows')||0).toLocaleString('pt-BR')+' contatos. Confira status e origem.';
}));



async function registryCoverage(){
 const root=$('registry');root.replaceChildren(el('p','Consultando base local…'));
 try{
  const r=await api('/api/registry/coverage?'+new URLSearchParams(new FormData($('registry-form'))));
  const grid=el('div',undefined,'metrics');
  for(const [label,key] of Object.entries({'Registros empresariais':'company_records','CNPJs válidos únicos':'unique_valid_cnpjs','Registros duplicados':'duplicate_valid_records','Sem CNPJ':'missing_cnpj_records','CNPJ inválido':'invalid_cnpj_records','Situação ativa registrada':'active_cnpjs','Não ativos':'inactive_cnpjs','Situação desconhecida':'unknown_status_cnpjs','Situação conflitante':'conflicting_status_cnpjs','Com fonte e data cadastral':'with_registry_source_and_date','Com perfil-alvo':'with_target_profile'})){
   const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',Number(r[key]).toLocaleString('pt-BR')));grid.append(card);
  }
  root.replaceChildren(grid,el('p',r.note),el('h3','Fontes por registro válido'));
  for(const [source,count] of Object.entries(r.sources_by_valid_record))root.append(el('p',source+' · '+count.toLocaleString('pt-BR')));
  root.append(el('h3','Idade da atualização cadastral local'));
  const ages={within_90_days:'Atualização local até 90 dias',older_than_90_days:'Atualização local acima de 90 dias',missing:'Sem fonte e data',future_date:'Data futura inconsistente'};
  for(const [key,label] of Object.entries(ages))root.append(el('p',label+' · '+Number(r.registry_update_age[key]).toLocaleString('pt-BR')));
  root.append(el('p','Data da atualização local não comprova competência ou atualidade da publicação da Receita.'),el('p','Cobertura do mercado: não calculada (sem denominador oficial comparável).'));
 }catch(e){root.replaceChildren(el('p','Inventário indisponível: '+e.message));throw e;}
}
$('registry-form').addEventListener('submit',e=>{e.preventDefault();run(registryCoverage);});


const qualificationLabels={priority_review:'Prioridade de revisão',evidence_contact_needed:'Evidência — verificar contato',contactable_prospect:'Prospect com canal',prospect_research:'Pesquisar prospect',registry_review:'Revisar cadastro',special_route:'Tratamento específico'};
let qualificationOffset=0,qualificationQuery=null;
async function loadQualification(){
 const root=$('qualification');
 $('qualification-prev').disabled=$('qualification-next').disabled=true;
 root.replaceChildren(el('p','Classificando registros locais…'));
 try{
  const qs=new URLSearchParams(qualificationQuery);qs.set('limit','50');qs.set('offset',String(qualificationOffset));
  const r=await api('/api/registry/qualification?'+qs);
  const grid=el('div',undefined,'metrics');
  for(const [key,label] of Object.entries(qualificationLabels)){const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',Number(r.counts[key]||0).toLocaleString('pt-BR')));grid.append(card);}
  root.replaceChildren(grid,el('p',r.note),el('p','Resultados do filtro: '+r.total.toLocaleString('pt-BR')));
  for(const x of r.items){
   const row=el('article',undefined,'record'),link=el('a','Abrir ficha empresarial');link.href='/#/empresa/'+encodeURIComponent(x.company_id);
   row.append(el('strong',x.name),el('p',x.cnpj+' · '+(x.profile_label||'Perfil não definido')),el('p',qualificationLabels[x.tier]),el('p','Canais: '+(x.channels.map(k=>channelNames[k]||k).join(', ')||'Nenhum')),el('p','Verificados: '+(x.verified_channels.map(k=>channelNames[k]||k).join(', ')||'Nenhum')),el('p','Evidências registradas: '+x.evidence_ids.length),link);root.append(row);
  }
  if(!r.items.length)root.append(el('p','Nenhum registro neste filtro.'));
  $('qualification-prev').disabled=qualificationOffset===0;
  $('qualification-next').disabled=qualificationOffset+50>=r.total;
  $('qualification-page').textContent='Página '+(qualificationOffset/50+1);
 }catch(e){root.replaceChildren(el('p',e.message));throw e;}
}
$('qualification-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{qualificationQuery=new URLSearchParams(new FormData(e.target));if(!qualificationQuery.get('tier'))qualificationQuery.delete('tier');qualificationOffset=0;await loadQualification();});});
$('qualification-prev').addEventListener('click',()=>run(async()=>{qualificationOffset=Math.max(0,qualificationOffset-50);await loadQualification();}));
$('qualification-next').addEventListener('click',()=>run(async()=>{qualificationOffset+=50;await loadQualification();}));


let targetsQuery=null,targetsOffset=0,preparedIds=[];
async function loadTargets(){
 const root=$('targets-results');preparedIds=[];
 $('targets-prev').disabled=$('targets-next').disabled=$('targets-prepare').disabled=true;
 root.replaceChildren(el('p','Consultando empresas…'));
 try{
 const qs=new URLSearchParams(targetsQuery);qs.set('limit','50');qs.set('offset',String(targetsOffset));
 const r=await api('/api/contacts/discovery-targets?'+qs);
 const grid=el('div',undefined,'metrics');
 for(const [label,key] of [['CNPJs ativos únicos','active_unique_cnpjs'],['Com canal','with_channel'],['Com canal verificado','with_verified_channel'],['Sem canal','missing_channel'],['Com site para pesquisa','ready_for_site_discovery']]){
  const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',Number(r[key]).toLocaleString('pt-BR')));grid.append(card);
 }
 root.replaceChildren(grid,el('p',r.note));
 for(const x of r.items){
 const row=el('article',undefined,'record'),link=el('a','Revisar ficha e canais');
 link.href='/#/empresa/'+encodeURIComponent(x.company_id);
 row.append(el('strong',x.name),el('p',x.cnpj+' · '+({registered_site:'Site cadastrado — revisar',conflicting_sites:'Sites conflitantes',missing_site:'Sem site cadastrado'}[x.reason]||x.reason)),link);
 if(x.discovery_ready){const label=el('label','Incluir após revisar titularidade'),check=el('input');check.type='checkbox';check.addEventListener('change',()=>{preparedIds=check.checked?[...new Set([...preparedIds,x.company_id])]:preparedIds.filter(id=>id!==x.company_id);$('targets-prepare').disabled=!preparedIds.length;});label.append(check);row.append(label);}
 root.append(row);
 }
 if(!r.items.length)root.append(el('p','Nenhum registro nesta página.'));
 $('targets-prev').disabled=targetsOffset===0;$('targets-next').disabled=targetsOffset+50>=r.missing_channel;$('targets-page').textContent='Página '+(targetsOffset/50+1);
 }catch(e){root.replaceChildren(el('p',e.message));throw e;}
}
$('targets-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{targetsQuery=new URLSearchParams(new FormData(e.target));targetsOffset=0;await loadTargets();});});
$('targets-prev').addEventListener('click',()=>run(async()=>{targetsOffset=Math.max(0,targetsOffset-50);await loadTargets();}));
$('targets-next').addEventListener('click',()=>run(async()=>{targetsOffset+=50;await loadTargets();}));
$('targets-prepare').addEventListener('click',()=>{if(!preparedIds.length)return;const input=$('create').elements.ids;if(input.value.trim()&&!confirm('Substituir a lista de IDs já preenchida?'))return;input.value=preparedIds.join(', ');input.focus();notice('IDs preparados. Confira e clique em Criar fila para confirmar.');});


async function loadWorkerDiagnostics(){
 const root=$('worker-diagnostics');root.replaceChildren(el('p','Consultando fila…'));
 try{
 const r=await api('/api/contacts/worker-diagnostics'),grid=el('div',undefined,'metrics');
 const metrics=[...Object.entries(labels).map(([key,label])=>[label,r.counts[key]]),
 ['Workers com atividade recente',r.recent_workers],['Reservas vencidas',r.expired_leases],['Reservas inconsistentes',r.missing_claim_metadata],
 ['Na fila sem tentativas disponíveis',r.exhausted_queued]];
 for(const [label,value] of metrics){const card=el('div',undefined,'metric');card.append(el('span',label),el('strong',Number(value).toLocaleString('pt-BR')));grid.append(card);}
 root.replaceChildren(grid,el('p',r.worker_verified?'Atividade recente registrada.':'Sem atividade recente confirmada.'),el('p','Último registro do worker: '+(r.last_worker_observed_at?new Date(r.last_worker_observed_at).toLocaleString('pt-BR'):'Nenhum')),el('p','Lote pendente mais antigo: '+(r.oldest_queued_job_at?new Date(r.oldest_queued_job_at).toLocaleString('pt-BR'):'Nenhum')),el('p',r.note),el('p','Consulta: '+new Date(r.observed_at).toLocaleString('pt-BR')));
 }catch(e){root.replaceChildren(el('p',e.message));throw e;}
}
$('worker-refresh').addEventListener('click',()=>run(loadWorkerDiagnostics));
