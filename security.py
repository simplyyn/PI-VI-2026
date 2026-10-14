import os
import secrets
import threading
from contextlib import asynccontextmanager
from fastapi import HTTPException
from auth import usuario_logado
from persistence import create_repository

@asynccontextmanager
async def lifespan(app):
    app.state.repository = create_repository()
    embedder = getattr(app.state.repository, 'embedder', None)
    if hasattr(embedder, 'warm_up'):
        # Em segundo plano: o servidor aceita requisições enquanto o modelo carrega.
        threading.Thread(target=embedder.warm_up, name='embeddings-warm-up', daemon=True).start()
    try:
        yield
    finally:
        if hasattr(app.state.repository, 'close'):
            app.state.repository.close()

def session_secret():
    value = os.getenv('SMARTDENT_SESSION_SECRET')
    if value and len(value) < 32:
        raise RuntimeError('SMARTDENT_SESSION_SECRET deve ter pelo menos 32 caracteres')
    if os.getenv('SMARTDENT_ENV') == 'production' and not value:
        raise RuntimeError('Configure SMARTDENT_SESSION_SECRET em produção')
    return value or secrets.token_urlsafe(48)

def require_user(request, roles):
    user = usuario_logado(request)
    if not user:
        raise HTTPException(401,'Autenticação necessária')
    if user['role'] not in roles:
        raise HTTPException(403,'Perfil sem permissão')
    if user['role'] != 'admin' and not user.get('empresa_id'):
        raise HTTPException(403,'Usuário sem clínica')
    return user

def csrf_check(request):
    expected = request.session.get('csrf')
    supplied = request.headers.get('X-CSRF-Token','')
    if not expected or not secrets.compare_digest(expected,supplied):
        raise HTTPException(403,'Token CSRF inválido')
