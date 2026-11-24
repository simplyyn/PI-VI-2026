(() => {
  const button = document.getElementById('asstBtn');
  const panel = document.getElementById('asstPanel');
  const header = panel.querySelector('.asst-head');
  const input = document.getElementById('asstInput');
  const close = document.getElementById('asstClose');
  const openKey = 'smartdent-asst-open';
  const sizeKey = 'smartdent-asst-size';
  const buttonKey = 'smartdent-asst-button-position';
  const panelKey = 'smartdent-asst-panel-position';
  const margin = 12;
  const composerGap = button.classList.contains('asst-btn--docked') ? 94 : margin;

  function read(key) {
    try { return JSON.parse(localStorage.getItem(key)); }
    catch { return null; }
  }

  function save(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  }

  function place(element, left, top) {
    element.classList.add('asst-positioned');
    const x = Math.max(margin, Math.min(left, innerWidth - element.offsetWidth - margin));
    const y = Math.max(margin, Math.min(top, innerHeight - element.offsetHeight - composerGap));
    element.style.left = `${x}px`;
    element.style.top = `${y}px`;
  }

  function restorePosition(element, key) {
    const saved = read(key);
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      place(element, saved.x, saved.y);
    }
  }

  function rememberPosition(element, key) {
    const { left, top } = element.getBoundingClientRect();
    save(key, { x: left, y: top });
  }

  function resetPosition(element, key) {
    element.classList.remove('asst-positioned');
    element.style.left = '';
    element.style.top = '';
    save(key, null);
  }

  function setOpen(open, moveFocus = true) {
    button.hidden = open;
    button.setAttribute('aria-expanded', String(open));
    panel.hidden = !open;
    restorePosition(open ? panel : button, open ? panelKey : buttonKey);
    // Keep the existing persisted open state compatible with earlier versions.
    save(openKey, open ? 1 : null);
    if (moveFocus) (open ? input : button).focus({ preventScroll: true });
  }

  function pointerGesture(handle, element, move, finish) {
    let gesture;
    handle.addEventListener('pointerdown', event => {
      if (gesture || !event.isPrimary || event.button !== 0) return;
      const targetButton = event.target.closest('button');
      if (targetButton && targetButton !== handle) return;
      handle.setPointerCapture(event.pointerId);
      gesture = {
        id: event.pointerId, x: event.clientX, y: event.clientY,
        rect: element.getBoundingClientRect(), moved: false
      };
    });
    handle.addEventListener('pointermove', event => {
      if (!gesture || event.pointerId !== gesture.id) return;
      const dx = event.clientX - gesture.x;
      const dy = event.clientY - gesture.y;
      if (!gesture.moved && Math.hypot(dx, dy) < 6) return;
      gesture.moved = true;
      move?.(gesture.rect, dx, dy);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      handle.addEventListener(type, event => {
        if (!gesture || event.pointerId !== gesture.id) return;
        const { moved } = gesture;
        gesture = null;
        finish(event, moved);
      });
    }
  }

  function isTouchTap(event, moved) {
    return !moved && event.type === 'pointerup' && event.pointerType === 'touch';
  }

  let draggedButton = false;
  function enableMove(handle, element, key) {
    pointerGesture(handle, element, ({ left, top }, dx, dy) => {
      element.classList.add('asst-dragging');
      place(element, left + dx, top + dy);
    }, (event, moved) => {
      if (!moved) {
        if (handle === button && isTouchTap(event, moved)) setOpen(true);
        return;
      }
      element.classList.remove('asst-dragging');
      rememberPosition(element, key);
      if (handle === button && event.type === 'pointerup') draggedButton = true;
    });
    handle.addEventListener('keydown', event => {
      if (event.target !== handle) return;
      if (event.key === 'Home') {
        event.preventDefault();
        resetPosition(element, key);
        return;
      }
      const direction = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
      if (!direction) return;
      event.preventDefault();
      const { left, top } = element.getBoundingClientRect();
      const step = event.shiftKey ? 48 : 12;
      place(element, left + direction[0] * step, top + direction[1] * step);
      rememberPosition(element, key);
    });
  }

  button.addEventListener('pointerdown', () => { draggedButton = false; });
  button.addEventListener('click', event => {
    if (panel.hidden && (!draggedButton || event.detail === 0)) setOpen(true);
    draggedButton = false;
  });
  close.addEventListener('click', () => {
    if (!panel.hidden) setOpen(false);
  });
  pointerGesture(close, close, null, (event, moved) => {
    if (isTouchTap(event, moved)) setOpen(false);
  });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') setOpen(false);
  });
  enableMove(button, button, buttonKey);
  enableMove(header, panel, panelKey);
  header.addEventListener('dblclick', event => {
    if (!event.target.closest('button')) resetPosition(panel, panelKey);
  });

  const size = read(sizeKey);
  if (size && size.w > 0 && size.h > 0) {
    panel.style.width = `${size.w}px`;
    panel.style.height = `${size.h}px`;
  }
  panel.querySelectorAll('.asst-resize').forEach(handle => {
    const horizontal = handle.dataset.dir.includes('l');
    const vertical = handle.dataset.dir.includes('t');
    handle.addEventListener('dblclick', () => {
      panel.style.width = '';
      panel.style.height = '';
      save(sizeKey, null);
      restorePosition(panel, panelKey);
    });
    pointerGesture(handle, panel, (rect, dx, dy) => {
      panel.classList.add('resizing');
      if (horizontal) panel.style.width = `${Math.min(rect.right - margin, Math.max(320, rect.width - dx))}px`;
      if (vertical) panel.style.height = `${Math.min(rect.bottom - margin, Math.max(300, rect.height - dy))}px`;
      place(panel, horizontal ? rect.right - panel.offsetWidth : rect.left,
        vertical ? rect.bottom - panel.offsetHeight : rect.top);
    }, (event, moved) => {
      if (!moved) return;
      panel.classList.remove('resizing');
      save(sizeKey, { w: panel.offsetWidth, h: panel.offsetHeight });
      rememberPosition(panel, panelKey);
    });
  });

  window.addEventListener('resize', () => {
    if (panel.hidden) restorePosition(button, buttonKey);
    else restorePosition(panel, panelKey);
  });
  setOpen(read(openKey) === 1, false);
})();
