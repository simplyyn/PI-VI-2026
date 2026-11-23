'use strict';

function answerRating(message, attendanceId, current, save) {
  if (message.autor !== 'ai' || !message.gerado_por_llm || !message.id) return null;
  const group = document.createElement('div');
  group.className = 'answer-rating';
  group.setAttribute('role', 'group');
  group.setAttribute('aria-label', 'Avaliar resposta da IA');
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  const choices = [true, false].map(useful => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = useful ? 'Útil' : 'Não foi útil';
    button.setAttribute('aria-pressed', String(current === useful));
    button.addEventListener('click', async () => {
      choices.forEach(choice => { choice.disabled = true; });
      try {
        const route = `/api/atendimentos/${attendanceId}/mensagens/${encodeURIComponent(message.id)}/avaliacao`;
        await save(route, 'PUT', { util: useful });
        choices.forEach((choice, index) => choice.setAttribute('aria-pressed', String((index === 0) === useful)));
        status.textContent = 'Avaliação registrada.';
      } catch (error) {
        status.textContent = error.message;
      } finally {
        choices.forEach(choice => { choice.disabled = false; });
      }
    });
    return button;
  });
  group.append(...choices, status);
  return group;
}
