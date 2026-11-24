'use strict';

const log = document.getElementById('demo-messages');
const compose = document.getElementById('portal-message-form');
const input = document.getElementById('demo-input');
const automatic = document.getElementById('customer-auto');
const feedback = document.getElementById('customer-feedback');
const startBooking = document.getElementById('start-booking');
const bookingOptions = document.getElementById('booking-options');
const bookingDate = document.getElementById('booking-date');
const bookingTimes = document.getElementById('booking-times');
const confirmation = document.getElementById('booking-confirmation');
const messageTime = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

let busy = false;
let initialized = false;
let version = '';
let retry;
let options = [];
let lastBookingId;

async function customerApi(path, method = 'GET', data) {
  const headers = {};
  if (method !== 'GET') {
    const session = await fetch('/api/session');
    if (!session.ok) throw Error('Entre novamente no sistema.');
    headers['X-CSRF-Token'] = (await session.json()).csrf_token;
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, { method, headers, ...(data ? { body: JSON.stringify(data) } : {}) });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Error(typeof body.detail === 'string' ? body.detail : 'Não foi possível concluir.');
  }
  return body;
}

function displayDate(isoDate) {
  return isoDate.split('-').reverse().join('/');
}

function renderTimes() {
  const day = options.find(option => option.data === bookingDate.value);
  bookingTimes.replaceChildren();
  for (const time of day?.horarios ?? []) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'portal-secondary';
    button.textContent = time;
    button.addEventListener('click', () => sendBooking(`${day.data} às ${time}`));
    bookingTimes.append(button);
  }
}

const pick = document.getElementById('booking-pick');
let dismissedPick = '';
let currentChoice = null;

function pickButton(title, subtitle, onClick, { initials, featured } = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'portal-pick' + (featured ? ' featured' : '');
  if (initials) {
    const avatar = document.createElement('span');
    avatar.className = 'av';
    avatar.textContent = initials;
    button.append(avatar);
  }
  const text = document.createElement('span');
  text.textContent = title;
  if (subtitle) {
    const small = document.createElement('small');
    small.textContent = subtitle;
    text.append(small);
  }
  button.append(text);
  button.addEventListener('click', onClick);
  return button;
}

// Passo 1: o que fazer. Passo 2: só os profissionais que fazem aquele procedimento.
function renderPick(action) {
  const estado = action?.estado;
  const key = JSON.stringify(action || null);
  const picking = (estado === 'escolher_procedimento' || estado === 'escolher_profissional') && key !== dismissedPick;
  pick.hidden = !picking;
  if (!picking) return;
  pick.dataset.key = key;
  const list = document.getElementById('pick-list');
  list.replaceChildren();
  if (estado === 'escolher_procedimento') {
    document.getElementById('pick-step').textContent = 'Passo 1 de 3';
    document.getElementById('pick-title').textContent = 'O que você gostaria de fazer?';
    for (const name of action.procedimentos || []) {
      const hint = name === 'Consulta de avaliação' ? 'Não sabe o que precisa? Comece por aqui.' : '';
      list.append(pickButton(name, hint, () => sendBooking(`Quero agendar ${name}`), { featured: !!hint }));
    }
  } else {
    document.getElementById('pick-step').textContent = 'Passo 2 de 3';
    document.getElementById('pick-title').textContent = `Quem faz ${action.procedimento.toLowerCase()}?`;
    for (const doctor of action.profissionais || []) {
      const initials = doctor.nome.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase();
      list.append(pickButton(doctor.nome, `${doctor.especialidades.join(' · ')} · ${doctor.duracao} min`,
        () => sendBooking(`Quero agendar ${action.procedimento} com ${doctor.nome}`), { initials }));
    }
    list.append(pickButton('Escolher outro procedimento', '', () => sendBooking('Quero agendar outro procedimento')));
  }
}

function renderBooking(action) {
  renderPick(action);
  const previousDate = bookingDate.value;
  options = action?.opcoes || [];
  if (action?.procedimento && action?.profissional) currentChoice = { procedimento: action.procedimento, profissional: action.profissional };
  if (!action || action.estado === 'concluido' || action.estado === 'cancelado') currentChoice = null;
  const recovering = action?.estado === 'erro' || action?.estado === 'coletando';
  bookingOptions.hidden = !options.length && !recovering;
  document.getElementById('booking-choices').hidden = !options.length;
  document.getElementById('options-title').textContent = options.length ? 'Escolha um horário' : 'Informe uma data e um horário';
  const summary = document.getElementById('booking-summary');
  summary.hidden = !currentChoice;
  if (currentChoice) {
    const text = document.getElementById('booking-summary-text');
    text.replaceChildren();
    const procedure = document.createElement('b');
    procedure.textContent = currentChoice.procedimento;
    text.append(procedure, ` com ${currentChoice.profissional}`);
  }
  confirmation.hidden = action?.estado !== 'aguardando_confirmacao';
  startBooking.hidden = !confirmation.hidden || !bookingOptions.hidden || !pick.hidden;
  bookingDate.replaceChildren(...options.map(day => new Option(displayDate(day.data), day.data)));
  if (options.some(day => day.data === previousDate)) bookingDate.value = previousDate;
  renderTimes();
}

function renderCustomer(data) {
  if (!initialized) {
    automatic.checked = data.status !== 'escalated';
    initialized = true;
  }
  const signature = JSON.stringify(data);
  if (signature === version) return;
  version = signature;
  lastBookingId = data.acao?.agendamento_id;
  renderBooking(data.acao);
  const review = confirmation.hidden ? null : data.mensagens.findLast(message =>
    message.acao?.estado === 'aguardando_confirmacao');
  document.getElementById('booking-review').textContent = review?.texto ?? '';
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
  const names = { client: 'Você', human: 'Equipe da clínica', ai: 'Assistente' };

  log.replaceChildren();
  if (!data.mensagens.length) {
    const intro = document.createElement('p');
    intro.textContent = 'Envie sua dúvida sobre preços, convênios ou procedimentos.';
    log.append(intro);
  }
  for (const message of data.mensagens) {
    if (message === review) continue;
    const row = document.createElement('div');
    row.className = message.autor === 'client' ? 'portal-message is-patient' : 'portal-message';
    const content = document.createElement('p');
    content.textContent = message.texto;
    const author = document.createElement('small');
    const date = new Date(message.criado_em);
    author.textContent = Number.isNaN(date.getTime()) ? names[message.autor] || 'Sistema' :
      `${names[message.autor] || 'Sistema'} · ${messageTime.format(date)}`;
    row.append(content, author);
    const rating = answerRating(message, data.atendimento_id, data.avaliacoes?.[message.id], customerApi);
    if (rating) row.append(rating);
    log.append(row);
  }
  if (nearBottom || busy) log.scrollTop = log.scrollHeight;

  renderAppointments(data.agendamentos || []);
}

// Cartões com borda colorida por situação: verde confirmada, âmbar (tracejada) pendente, azul realizada, vermelha cancelada.
const STATUS_LABEL = { confirmado: 'Confirmada', pendente: 'Pendente', cancelado: 'Cancelada', realizado: 'Realizada' };
const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const WEEKDAYS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

function appointmentCard(appointment) {
  const status = appointment.realizado_em ? 'realizado' : appointment.status;
  const [year, month, day] = appointment.data.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const start = appointment.horario.slice(0, 5);
  const [h, m] = start.split(':').map(Number);
  const endMinutes = h * 60 + m + (appointment.duracao || 0);
  const end = `${String(Math.floor(endMinutes / 60)).padStart(2, '0')}:${String(endMinutes % 60).padStart(2, '0')}`;

  const card = document.createElement('div');
  card.className = `appt ${status}`;
  card.title = `${STATUS_LABEL[status] || status} · ${displayDate(appointment.data)}`;
  const dayBox = document.createElement('div');
  dayBox.className = 'day';
  const dayNumber = document.createElement('b');
  dayNumber.textContent = day;
  const dayMeta = document.createElement('small');
  dayMeta.textContent = `${WEEKDAYS[date.getDay()]} · ${MONTHS[month - 1]}`;
  dayBox.append(dayNumber, dayMeta);
  const info = document.createElement('div');
  info.className = 'info';
  const procedure = document.createElement('b');
  procedure.textContent = appointment.procedimento;
  const detail = document.createElement('span');
  detail.textContent = `${start}–${end} · ${appointment.dentista}`;
  info.append(procedure, detail);
  const chip = document.createElement('span');
  chip.className = 'chip';
  chip.textContent = STATUS_LABEL[status] || status;
  card.append(dayBox, info, chip);
  return card;
}

function renderAppointments(list) {
  const box = document.getElementById('customer-appointments');
  box.replaceChildren();
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const upcoming = list.filter(a => a.data >= today && !a.realizado_em && a.status !== 'cancelado')
    .sort((x, y) => (x.data + x.horario).localeCompare(y.data + y.horario));
  const past = list.filter(a => !upcoming.includes(a))
    .sort((x, y) => (y.data + y.horario).localeCompare(x.data + x.horario));
  document.getElementById('appointments-count').textContent = upcoming.length;
  if (!list.length) {
    const none = document.createElement('p');
    none.className = 'none';
    none.textContent = 'Nenhum agendamento ainda. Use “Agendar consulta” para marcar.';
    box.append(none);
    return;
  }
  for (const [title, rows] of [['Próximas', upcoming], ['Histórico', past.slice(0, 5)]]) {
    if (!rows.length) continue;
    const label = document.createElement('div');
    label.className = 'group';
    label.textContent = title;
    box.append(label, ...rows.map(appointmentCard));
  }
}

async function refreshCustomer() {
  if (busy || document.hidden) return;
  try {
    const data = await customerApi('/api/cliente/conversa');
    if (!busy) renderCustomer(data);
  } catch (error) {
    if (!busy) feedback.textContent = error.message;
  }
}

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  if (!retry || retry.texto !== text) {
    retry = { texto: text, request_id: crypto.randomUUID(), resposta_automatica: automatic.checked };
  }

  busy = true;
  input.disabled = document.getElementById('send-message').disabled = true;
  const previousBookingId = lastBookingId;
  feedback.textContent = 'Registrando mensagem…';
  try {
    const data = await customerApi('/api/cliente/mensagens', 'POST', retry);
    renderCustomer(data);
    input.value = '';
    retry = undefined;
    const justBooked = data.acao?.estado === 'concluido' && previousBookingId !== lastBookingId;
    feedback.textContent = data.aviso || (justBooked ? 'Agendamento confirmado.' : '');
    if (!confirmation.hidden) document.getElementById('confirm-booking').focus();
    else if (options.length) bookingDate.focus();
    else {
      input.disabled = false;
      input.focus();
    }
  } catch (error) {
    input.value = text;
    feedback.textContent = error.message + ' Você pode tentar enviar novamente.';
  } finally {
    busy = false;
    input.disabled = document.getElementById('send-message').disabled = false;
  }
}

async function enableAutomatic() {
  busy = true;
  try {
    const data = await customerApi('/api/cliente/retomar', 'POST', {});
    automatic.checked = true;
    renderCustomer(data);
    return true;
  } catch (error) {
    automatic.checked = false;
    feedback.textContent = error.message;
    return false;
  } finally {
    busy = false;
  }
}

async function sendBooking(text) {
  if (busy) return;
  if (automatic.checked || await enableAutomatic()) await send(text);
}

compose.addEventListener('submit', event => {
  event.preventDefault();
  send(input.value);
});
bookingDate.addEventListener('change', renderTimes);
startBooking.addEventListener('click', () => {
  dismissedPick = '';
  version = ''; // força redesenhar mesmo que a resposta seja igual à anterior
  sendBooking('Quero agendar uma consulta');
});
document.getElementById('confirm-booking').addEventListener('click', () => sendBooking('confirmar'));
document.getElementById('discard-pick').addEventListener('click', () => {
  // A escolha ainda não abriu rascunho no servidor: basta fechar o painel.
  dismissedPick = pick.dataset.key || '';
  pick.hidden = true;
  startBooking.hidden = !confirmation.hidden || !bookingOptions.hidden;
});
document.getElementById('change-procedure').addEventListener('click', () => sendBooking('Quero agendar outro procedimento'));
for (const id of ['cancel-booking', 'discard-options']) {
  document.getElementById(id).addEventListener('click', () => sendBooking('cancelar'));
}
document.getElementById('clear-chat').addEventListener('click', async () => {
  if (busy) return;
  if (!confirm('Apagar todas as mensagens desta conversa? As consultas já agendadas continuam na agenda.')) return;
  busy = true;
  try {
    const data = await customerApi('/api/cliente/limpar', 'POST', {});
    version = '';
    initialized = false;
    retry = undefined;
    renderCustomer(data);
    feedback.textContent = 'Conversa apagada. Você pode começar de novo.';
    input.focus();
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    busy = false;
  }
});
automatic.addEventListener('change', () => {
  if (automatic.checked && !busy) enableAutomatic();
});

const appearance = document.getElementById('btn-dark-toggle');
appearance.setAttribute('aria-pressed', String(document.documentElement.classList.contains('dark')));
appearance.addEventListener('click', () => {
  const dark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('smartdent-dark', dark ? '1' : '0');
  appearance.setAttribute('aria-pressed', String(dark));
});

refreshCustomer();
setInterval(refreshCustomer, 4000);
