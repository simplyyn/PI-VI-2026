import hashlib
import hmac
import secrets
from fastapi.responses import RedirectResponse

def hash_password(password):
    if not 12 <= len(password) <= 256:
        raise ValueError('Senha deve ter entre 12 e 256 caracteres')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000)
    return 'pbkdf2_sha256$600000$' + salt.hex() + '$' + digest.hex()

def verify_password(password, encoded):
    if len(password) > 256:
        return False
    try:
        algorithm, iterations, salt, digest = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or iterations != '600000':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False

DUMMY_HASH = hash_password(secrets.token_urlsafe(24))

def autenticar(email, senha, repository):
    user = repository.user(email)
    valid = verify_password(senha, user['password_hash'] if user else DUMMY_HASH)
    return user if user and valid else None

def usuario_logado(request):
    identifier = request.session.get('user_id')
    user = request.app.state.repository.user_by_id(identifier) if identifier is not None else None
    if user:
        user.pop('password_hash', None)
    return user

def redirecionar_por_role(role):
    return RedirectResponse({'admin':'/admin','owner':'/','customer':'/chat'}.get(role,'/login'),status_code=302)
