'use strict';

const themeButton = document.getElementById('btn-dark-toggle');
if (themeButton) {
  const root = document.documentElement;
  themeButton.setAttribute('aria-pressed', String(root.classList.contains('dark')));
  themeButton.addEventListener('click', () => {
    const dark = root.classList.toggle('dark');
    themeButton.setAttribute('aria-pressed', String(dark));
    localStorage.setItem('smartdent-dark', dark ? '1' : '0');
  });
}

const menuButton = document.querySelector('.menu-toggle');
if (menuButton) {
  menuButton.addEventListener('click', () => {
    const open = menuButton.closest('.sidebar').classList.toggle('menu-open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
}
