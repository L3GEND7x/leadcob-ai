'use strict';
(() => {
 const nav=document.getElementById('nav'), toggle=document.getElementById('nav-toggle');
 const mobile=window.matchMedia('(max-width: 860px)');
 function sync(open=false){
   toggle.setAttribute('aria-expanded',String(mobile.matches && open));
   nav.classList.toggle('menu-open',mobile.matches && open);
   nav.inert=mobile.matches && !open;
 }
 toggle.addEventListener('click',()=>sync(toggle.getAttribute('aria-expanded')!=='true'));
 mobile.addEventListener('change',()=>sync());
 nav.addEventListener('click',e=>{if(e.target.closest('a')&&mobile.matches){sync();toggle.focus();}});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&toggle.getAttribute('aria-expanded')==='true'){sync();toggle.focus();}});
 document.querySelector('.skip-link').addEventListener('click',e=>{e.preventDefault();document.getElementById('view').focus();});
 sync();
})();
