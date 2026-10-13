document.addEventListener('click', async event => {
  const link = event.target.closest('a[href="/logout"]');
  if (!link) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  try {
    const session = await fetch('/api/session').then(r => { if (!r.ok) throw Error(); return r.json(); });
    const response = await fetch('/logout', {method:'POST', headers:{'X-CSRF-Token':session.csrf_token}});
    if (!response.ok) throw Error();
    window.location.href = '/login';
  } catch (_) { alert('Não foi possível encerrar a sessão.'); }
}, true);
