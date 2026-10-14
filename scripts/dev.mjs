// Atalhos de desenvolvimento: `npm run dev` (servidor com reload), `npm test` (suíte unittest) e
// `npm run manage -- <comando>` (manage.py com o mesmo banco do .env).
// O backend é Python; este script só encontra o venv, carrega o .env local e chama o Python.
// A aplicação em si não lê .env: em produção, configure as variáveis no processo.
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const bin = process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];

function readDotEnv(file) {
  if (!existsSync(file)) return {};
  const values = {};
  for (const raw of readFileSync(file, 'utf8').replace(/^﻿/, '').split(/\r?\n/)) {
    const line = raw.trim();
    const eq = line.indexOf('=');
    if (!line || line.startsWith('#') || eq <= 0) continue;
    const value = line.slice(eq + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
    if (value) values[line.slice(0, eq).trim()] = value;
  }
  return values;
}

// Prioridade: variáveis do terminal > .env > padrões abaixo. Valores vazios contam como ausentes.
const env = { ...process.env };
const defaults = {
  SMARTDENT_ENV: 'development',
  FASTEMBED_CACHE_PATH: path.join(homedir(), '.cache', 'fastembed'),
  // Fixo durante esta execução: o --reload não derruba a sessão a cada alteração de código.
  SMARTDENT_SESSION_SECRET: randomBytes(48).toString('base64url'),
};
for (const [key, value] of Object.entries({ ...defaults, ...readDotEnv(path.join(root, '.env')) })) {
  if (!env[key]) env[key] = value;
}

const candidates = [env.SMARTDENT_PYTHON, path.join(root, '.venv', ...bin), path.join(homedir(), '.venvs', 'smartdent', ...bin)];
const python = candidates.find((candidate) => candidate && existsSync(candidate));
if (!python) {
  console.error('Python do projeto não encontrado. Crie o venv (Python 3.12) em .venv ou ~/.venvs/smartdent,');
  console.error('instale requirements-dev.txt nele, ou defina SMARTDENT_PYTHON no .env.');
  process.exit(1);
}

const [command, ...rest] = process.argv.slice(2);
const port = env.SMARTDENT_PORT || '8000';
const args = {
  test: ['-m', 'unittest', 'discover', '-s', 'tests', ...rest],
  manage: ['manage.py', ...rest],
}[command] ?? ['-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', port, '--reload'];
if (command === undefined) {
  const database = env.SMARTDENT_DATABASE_URL ? 'PostgreSQL' : `SQLite (${env.SMARTDENT_DB_PATH || 'data/smartdent.sqlite3'})`;
  console.log(`SmartDent: http://127.0.0.1:${port}/login | banco: ${database} | Ctrl+C para parar`);
}

const child = spawn(python, args, { cwd: root, env, stdio: 'inherit' });
// Ctrl+C chega também ao Python (mesmo console); o Node espera ele encerrar e devolve o código de saída.
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => {});
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
