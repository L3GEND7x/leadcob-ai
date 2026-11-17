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
 actions.append(btn('Gerenciar usuários',()=>showMembers(org,details)),btn(org.active?'Suspender':'Reativar',async()=>{
 if(!confirm(org.active?'Suspender e encerrar todas as sessões desta organização?':'Reativar esta organização?'))return;
 await api(base+'/'+org.id,'PATCH',{active:!org.active});await load();
 }));r.append(actions,details);$('rows').append(r);}
 if(!rows.length)$('rows').append(el('p','Nenhuma organização nesta página.'));
 $('prev').disabled=offset===0;$('next').disabled=rows.length<limit;$('page').textContent='Página '+(offset/limit+1);
}
$('provision').addEventListener('submit',e=>{e.preventDefault();run(async()=>{let data;try{data=await api(base,'POST',Object.fromEntries(new FormData(e.target)));}finally{e.target.elements.password.value='';}e.target.reset();offset=0;await load();alert('Organização criada. Código de acesso: '+data.id);});});
$('refresh').addEventListener('click',()=>run(load));$('prev').addEventListener('click',()=>run(async()=>{offset=Math.max(0,offset-limit);await load();}));$('next').addEventListener('click',()=>run(async()=>{offset+=limit;await load();}));
run(async()=>{const s=await api('/api/auth/session');if(!s.authenticated||s.mode!=='cloud'||!s.csrf_token)throw Error('Entre no painel principal com a conta do proprietário.');csrf=s.csrf_token;await load();$('directory').hidden=false;$('admin-content').hidden=false;});
