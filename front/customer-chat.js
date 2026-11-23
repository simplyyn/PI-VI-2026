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

function renderBooking(action) {
  const previousDate = bookingDate.value;
  options = action?.opcoes || [];
  const recovering = action?.estado === 'erro' || action?.estado === 'coletando';
  bookingOptions.hidden = !options.length && !recovering;
  document.getElementById('booking-choices').hidden = !options.length;
  document.getElementById('options-title').textContent = options.length ? 'Escolha um horário' : 'Informe uma data e um horário';
  confirmation.hidden = action?.estado !== 'aguardando_confirmacao';
  startBooking.hidden = !confirmation.hidden || !bookingOptions.hidden;
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

  const appointments = document.getElementById('customer-appointments');
  appointments.replaceChildren();
  if (!data.agendamentos?.length) appointments.textContent = 'Nenhum agendamento registrado.';
  for (const appointment of data.agendamentos || []) {
    const row = document.createElement('p');
    const status = appointment.realizado_em ? 'realizado' : appointment.status;
    row.textContent = `${displayDate(appointment.data)} às ${appointment.horario.slice(0, 5)} · ${appointment.procedimento} · ${appointment.dentista} (${status})`;
    appointments.append(row);
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
startBooking.addEventListener('click', () => sendBooking('Quero agendar uma consulta'));
document.getElementById('confirm-booking').addEventListener('click', () => sendBooking('confirmar'));
for (const id of ['cancel-booking', 'discard-options']) {
  document.getElementById(id).addEventListener('click', () => sendBooking('cancelar'));
}
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
