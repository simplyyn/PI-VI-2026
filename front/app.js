/* SmartDent — comportamento compartilhado + camada de ações (CRUD/LLM) */
(function(){
  const html = document.documentElement;

  function applyTheme(t){
    html.setAttribute('data-theme', t);
    const icon = document.getElementById('themeIcon');
    if (icon) icon.setAttribute('data-lucide', t === 'dark' ? 'sun' : 'moon');
    if (window.lucide) lucide.createIcons();
    localStorage.setItem('smartdent-tema', t);
  }

  // ── CSRF + chamadas de API ──
  let _csrf = null;
  async function csrf(){
    if (_csrf) return _csrf;
    const r = await fetch('/api/session');
    if (!r.ok) throw new Error('Sua sessão expirou. Entre novamente.');
    _csrf = (await r.json()).csrf_token;
    return _csrf;
  }
  async function api(method, url, body){
    const headers = { 'X-CSRF-Token': await csrf() };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const r = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    const data = await r.json().catch(()=>({}));
    if (!r.ok){
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = msg.map(e=>e.msg||'').join('; ');
      throw new Error(typeof msg === 'string' && msg ? msg : 'Operação inválida.');
    }
    return data;
  }

  // ── Toast ──
  function toast(message, kind){
    let host = document.getElementById('sd-toasts');
    if (!host){ host = document.createElement('div'); host.id = 'sd-toasts'; document.body.appendChild(host); }
    const el = document.createElement('div');
    el.className = 'sd-toast ' + (kind || 'info');
    el.textContent = message;
    host.appendChild(el);
    setTimeout(()=>{ el.classList.add('out'); setTimeout(()=>el.remove(), 250); }, 3600);
  }

  // ── Diálogo de formulário ──
  function openForm(cfg){
    const overlay = document.createElement('div');
    overlay.className = 'sd-modal-overlay';
    const fields = cfg.fields.map(f=>{
      const id = 'f_'+f.name;
      let control;
      if (f.type === 'select'){
        control = `<select id="${id}" name="${f.name}">`+
          f.options.map(o=>`<option value="${o.value}" ${String(o.value)===String(f.value??'')?'selected':''}>${o.label}</option>`).join('')+`</select>`;
      } else if (f.type === 'textarea'){
        control = `<textarea id="${id}" name="${f.name}" rows="5" placeholder="${f.placeholder||''}">${f.value!=null?String(f.value):''}</textarea>`;
      } else if (f.type === 'checkbox'){
        control = `<label class="sd-check"><input type="checkbox" id="${id}" name="${f.name}" ${f.value?'checked':''}> ${f.checkLabel||'Ativo'}</label>`;
      } else {
        control = `<input id="${id}" name="${f.name}" type="${f.type||'text'}" value="${f.value!=null?String(f.value):''}" placeholder="${f.placeholder||''}" ${f.step?`step="${f.step}"`:''} ${f.required?'required':''}>`;
      }
      return `<div class="field"><label for="${id}">${f.label}${f.required?' *':''}</label>${control}</div>`;
    }).join('');
    overlay.innerHTML = `<div class="sd-modal" role="dialog" aria-modal="true">
      <h3>${cfg.title}</h3>
      <form class="sd-form">${fields}
        <div class="sd-modal-actions">
          <button type="button" class="btn-ghost" data-cancel>Cancelar</button>
          <button type="submit" class="btn-primary">${cfg.submitLabel||'Salvar'}</button>
        </div>
      </form></div>`;
    document.body.appendChild(overlay);
    const close = ()=>overlay.remove();
    overlay.addEventListener('click', e=>{ if (e.target===overlay) close(); });
    overlay.querySelector('[data-cancel]').onclick = close;
    overlay.querySelector('.sd-form').addEventListener('submit', async e=>{
      e.preventDefault();
      const body = {};
      for (const f of cfg.fields){
        const el = overlay.querySelector(`[name="${f.name}"]`);
        let v = f.type === 'checkbox' ? el.checked : el.value;
        if (f.type === 'number' || f.numeric){ v = v === '' ? (f.optional?null:0) : Number(v); }
        else if (f.type === 'date'){ v = v === '' ? null : v; }
        else if (typeof v === 'string'){ v = v.trim(); }
        if (f.omitEmpty && (v === '' || v == null)) continue;
        body[f.name] = v;
      }
      if (cfg.transform) cfg.transform(body);
      const btn = overlay.querySelector('button[type=submit]');
      btn.disabled = true;
      try {
        await api(cfg.submit.method, cfg.submit.url, body);
        toast(cfg.okMessage || 'Salvo com sucesso.', 'ok');
        close();
        (cfg.onOk || (()=>location.reload()))();
      } catch (err){ btn.disabled = false; toast(err.message, 'err'); }
    });
    setTimeout(()=>{ const first = overlay.querySelector('input,select,textarea'); if (first) first.focus(); }, 30);
  }

  async function del(url, label){
    if (!confirm(label || 'Confirmar exclusão? Esta ação não pode ser desfeita.')) return;
    try { await api('DELETE', url); toast('Excluído.', 'ok'); location.reload(); }
    catch (err){ toast(err.message, 'err'); }
  }

  async function doLogout(){
    try { await api('POST', '/logout'); } catch(e){}
    location.href = '/login';
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) lucide.createIcons();
    applyTheme(localStorage.getItem('smartdent-tema') || 'light');
    const btn = document.getElementById('themeBtn');
    if (btn) btn.onclick = () => applyTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');

    const toggleGroups = (sel, itemSel) => {
      document.querySelectorAll(sel).forEach(group => {
        const items = group.querySelectorAll(itemSel);
        items.forEach(it => it.addEventListener('click', e => {
          if (it.tagName === 'A' && it.getAttribute('href') && it.getAttribute('href') !== '#') return;
          e.preventDefault();
          items.forEach(x => x.classList.remove('active'));
          it.classList.add('active');
        }));
      });
    };
    toggleGroups('.tabs', 'button');
    toggleGroups('.filters', 'button');
    toggleGroups('.topnav', 'a');

    document.querySelectorAll('[data-select-group]').forEach(group => {
      const items = group.querySelectorAll('[data-select]');
      items.forEach(it => it.addEventListener('click', () => {
        items.forEach(x => x.classList.remove('active'));
        it.classList.add('active');
      }));
    });
  });

  window.SmartDent = { applyTheme, api, csrf, toast, openForm, del };
  window.doLogout = doLogout;
})();
