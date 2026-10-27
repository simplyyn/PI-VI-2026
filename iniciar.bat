@echo off
rem Inicia o SmartDent localmente e abre o navegador. Duplo clique para rodar; feche a janela (ou Ctrl+C) para parar.
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem ── Variaveis do .env (valores vazios ficam de fora) ──
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if not "%%b"=="" set "%%a=%%b"
  )
)
if not defined SMARTDENT_ENV set "SMARTDENT_ENV=development"
if not defined SMARTDENT_PORT set "SMARTDENT_PORT=8000"
if not defined FASTEMBED_CACHE_PATH set "FASTEMBED_CACHE_PATH=%USERPROFILE%\.cache\fastembed"
set "URL=http://127.0.0.1:%SMARTDENT_PORT%/login"

rem ── Python do projeto: SMARTDENT_PYTHON, .venv ou ~/.venvs/smartdent; senao cria o .venv ──
set "PY=%SMARTDENT_PYTHON%"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "%USERPROFILE%\.venvs\smartdent\Scripts\python.exe" set "PY=%USERPROFILE%\.venvs\smartdent\Scripts\python.exe"
if not defined PY (
  echo Criando ambiente virtual .venv e instalando dependencias...
  python -m venv .venv || goto :erro_python
  ".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt || goto :erro_pip
  set "PY=.venv\Scripts\python.exe"
)

rem ── Se ja estiver rodando, so abre o navegador ──
"%PY%" -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1',%SMARTDENT_PORT%))==0 else 1)"
if not errorlevel 1 (
  echo SmartDent ja esta rodando. Abrindo %URL%
  start "" "%URL%"
  exit /b 0
)

rem ── PostgreSQL fora do ar: usa o SQLite local ──
if defined SMARTDENT_DATABASE_URL (
  "%PY%" -c "import os,socket,sys,urllib.parse as u; p=u.urlparse(os.environ['SMARTDENT_DATABASE_URL']); s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex((p.hostname or '127.0.0.1',p.port or 5432))==0 else 1)"
  if errorlevel 1 (
    echo PostgreSQL indisponivel; usando o SQLite local.
    set "SMARTDENT_DATABASE_URL="
  )
)
rem Com SQLite a busca automatica fica "pending" e o chat nao responde; usa a busca por palavras-chave.
if not defined SMARTDENT_DATABASE_URL if not defined SMARTDENT_RETRIEVAL set "SMARTDENT_RETRIEVAL=local_keyword"

rem Chave de sessao fixa durante esta execucao (o --reload nao derruba o login).
if not defined SMARTDENT_SESSION_SECRET (
  for /f "usebackq delims=" %%s in (`call "%PY%" -c "import secrets; print(secrets.token_urlsafe(48))"`) do set "SMARTDENT_SESSION_SECRET=%%s"
)

rem ── Abre o navegador assim que o servidor responder ──
start "" /b "%PY%" -c "import socket,time,webbrowser; ok=lambda: socket.socket().connect_ex(('127.0.0.1',%SMARTDENT_PORT%))==0; any(ok() or time.sleep(0.5) for _ in range(240)) and webbrowser.open('%URL%')"

echo.
echo SmartDent: %URL%
echo Feche esta janela ou aperte Ctrl+C para parar.
echo.
"%PY%" -m uvicorn app:app --host 127.0.0.1 --port %SMARTDENT_PORT% --reload
exit /b %errorlevel%

:erro_python
echo Nao foi possivel criar o .venv. Instale o Python 3.12 e tente de novo.
pause
exit /b 1

:erro_pip
echo Falha ao instalar as dependencias (requirements-dev.txt).
pause
exit /b 1
