let csrfToken = '';
async function sessionReady() {
  const response = await fetch('/api/auth/session');
  if (!response.ok) throw Error('Não foi possível verificar o acesso.');
  const session = await response.json();
  csrfToken = session.csrf_token || '';
  if (session.authenticated) return true;
  const layout = document.querySelector('.layout');
  layout.hidden = true;
  let box = document.getElementById('login-box');
  if (!box) {
    box = document.createElement('main'); box.id = 'login-box'; box.style.cssText = 'max-width:440px;margin:8vh auto;padding:24px';
    box.innerHTML = '<h1>LeadCob AI</h1><p>Acesse seu ambiente de trabalho.</p><form id="login-form" class="form"><label class="f">Usuário<input name="username" autocomplete="username" required></label><label class="f">Senha<input name="password" type="password" autocomplete="current-password" required></label><button class="primary">Entrar</button><p id="login-error" role="alert"></p></form>';
    document.body.append(box);
  }
  document.getElementById('login-form').onsubmit = async event => {
    event.preventDefault(); const form = event.target; form.querySelector('button').disabled = true;
    try {
      const r = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))});
      const data = await r.json();
      if (!r.ok) throw Error(data.detail || 'Falha no acesso.');
      csrfToken = data.csrf_token; box.remove(); layout.hidden = false; route();
    } catch (error) { document.getElementById('login-error').textContent = error.message; }
    finally { form.querySelector('button').disabled = false; }
  };
  return false;
}
async function logout() {
  await fetch('/api/auth/logout', {method:'POST', headers: {'X-CSRF-Token': csrfToken}});
  location.reload();
}
