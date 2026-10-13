(() => {
  'use strict';
  const resource = document.getElementById('crud-root').dataset.resource;
  const isStock = resource === 'estoque';
  const records = new Map(JSON.parse(document.getElementById('crud-records').textContent).map(r => [String(r.id), r]));
  const endpoint = '/api/' + resource;
  const dialog = document.getElementById('crud-dialog');
  const form = document.getElementById('crud-form');
  const fields = document.getElementById('crud-fields');
  const error = document.getElementById('crud-error');
  const save = document.getElementById('crud-save');
  let action, identifier, busy = false;

  async function request(url, method, data) {
    const sessionResponse = await fetch('/api/session');
    if (!sessionResponse.ok) throw Error('Sua sessão expirou. Entre novamente.');
    const session = await sessionResponse.json();
    const response = await fetch(url, {
      method, headers: {'Content-Type':'application/json', 'X-CSRF-Token':session.csrf_token},
      ...(data === undefined ? {} : {body:JSON.stringify(data)})
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = body.detail;
      throw Error(Array.isArray(detail) ? detail.map(e => `${e.loc.at(-1)}: ${e.msg}`).join('; ') : detail || 'Não foi possível salvar. Tente novamente.');
    }
  }

  function addField(name, label, type, value, maximum) {
    const wrapper = document.createElement('label');
    wrapper.textContent = label;
    const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
    input.name = name;
    if (type !== 'textarea') input.type = type;
    if (type === 'checkbox') input.checked = value ?? true;
    else {
      input.value = value ?? '';
      input.required = true;
      if (type === 'number') { input.step = '1'; input.min = name === 'delta' ? '-1000000000' : '0'; input.max = '1000000000'; }
      else input.maxLength = maximum;
    }
    wrapper.append(input);
    fields.append(wrapper);
  }

  function open(mode, id) {
    action = mode; identifier = id;
    error.textContent = ''; fields.replaceChildren();
    const record = records.get(id) || {};
    document.getElementById('crud-title').textContent = mode === 'move' ? 'Movimentar estoque' : `${mode === 'edit' ? 'Editar' : 'Cadastrar'} ${isStock ? 'item' : 'artigo'}`;
    if (mode === 'move') {
      const help = document.createElement('p');
      help.textContent = `${record.nome}: saldo ${record.quantidade}. Use um número positivo para entrada ou negativo para saída.`;
      fields.append(help);
      addField('delta', 'Quantidade da movimentação', 'number', '', 0);
    } else if (isStock) {
      addField('nome', 'Nome', 'text', record.nome, 200);
      addField('categoria', 'Categoria', 'text', record.categoria, 100);
      addField('unidade', 'Unidade', 'text', record.unidade, 100);
      addField('quantidade', 'Quantidade', 'number', record.quantidade ?? 0);
      addField('minimo', 'Quantidade mínima', 'number', record.minimo ?? 0);
    } else {
      addField('titulo', 'Título', 'text', record.titulo, 200);
      addField('categoria', 'Categoria', 'text', record.categoria, 100);
      addField('conteudo', 'Conteúdo usado pelo assistente', 'textarea', record.conteudo, 20000);
      addField('status', 'Artigo ativo', 'checkbox', record.status);
    }
    dialog.showModal();
    fields.querySelector('input,textarea').focus();
  }

  document.getElementById('crud-cancel').addEventListener('click', () => { if (!busy) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const payload = {};
    for (const input of fields.querySelectorAll('input,textarea')) {
      payload[input.name] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value.trim();
      if (input.required && typeof payload[input.name] === 'string' && !payload[input.name]) { error.textContent = 'Preencha todos os campos.'; return; }
    }
    if (action === 'move' && !payload.delta) { error.textContent = 'Informe uma movimentação diferente de zero.'; return; }
    busy = true; save.disabled = true; error.textContent = '';
    try {
      const url = action === 'create' ? endpoint : endpoint + '/' + identifier + (action === 'move' ? '/movimentacoes' : '');
      await request(url, action === 'edit' ? 'PUT' : 'POST', payload);
      window.location.reload();
    } catch (exception) { error.textContent = exception.message; }
    finally { busy = false; save.disabled = false; }
  });

  document.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button || button.disabled) return;
    const mode = button.dataset.action;
    const id = button.closest('tr')?.dataset.id;
    if (mode !== 'delete') { open(mode, id); return; }
    if (!confirm('Excluir este registro? Esta ação não pode ser desfeita.')) return;
    button.disabled = true;
    try { await request(endpoint + '/' + id, 'DELETE'); window.location.reload(); }
    catch (exception) { document.getElementById('crud-feedback').textContent = exception.message; button.disabled = false; }
  });

  document.addEventListener('change', async event => {
    const toggle = event.target.closest('input[data-action="status"]');
    if (!toggle) return;
    const id = toggle.closest('tr').dataset.id;
    const record = records.get(id);
    toggle.disabled = true;
    try {
      await request(endpoint + '/' + id, 'PUT', {titulo:record.titulo,categoria:record.categoria,conteudo:record.conteudo,status:toggle.checked});
      record.status = toggle.checked;
    } catch (exception) { toggle.checked = record.status; document.getElementById('crud-feedback').textContent = exception.message; }
    finally { toggle.disabled = false; }
  });

  let category = 'Todos';
  const search = document.querySelector('.kb-search');
  function filter() {
    const query = search.value.trim().toLocaleLowerCase('pt-BR');
    for (const row of document.querySelectorAll('tr[data-id]')) {
      const record = records.get(row.dataset.id);
      row.hidden = !(category === 'Todos' || record.categoria === category) || !`${record.nome || record.titulo} ${record.categoria}`.toLocaleLowerCase('pt-BR').includes(query);
    }
  }
  search.addEventListener('input', filter);
  for (const tab of document.querySelectorAll('.filter-tab')) tab.addEventListener('click', () => {
    document.querySelector('.filter-tab.active')?.classList.remove('active');
    tab.classList.add('active'); category = tab.textContent.trim(); filter();
  });
})();
