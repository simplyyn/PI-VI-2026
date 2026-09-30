# auth.py
# Banco em memória — estrutura pronta para trocar por MongoDB
# Quando migrar: substituir USERS por consultas ao Motor/PyMongo

USERS = {
    "admin@smartbiz.com": {
        "id": "u_001",
        "nome": "Equipe SmartBiz",
        "iniciais": "SB",
        "role": "admin",
        "senha": "admin123",
    },
    "joao@padaria.com": {
        "id": "u_002",
        "nome": "João Silva",
        "iniciais": "JS",
        "role": "owner",
        "senha": "dono123",
        "empresa": "Padaria do João",
        "empresa_id": "padaria-do-joao",
        "plano": "Pro",
    },
    "maria@cliente.com": {
        "id": "u_003",
        "nome": "Maria Santos",
        "iniciais": "MS",
        "role": "customer",
        "senha": "cliente123",
        "empresa_id": "padaria-do-joao",
        "empresa_nome": "Padaria do João",
    },
}


def autenticar(email: str, senha: str):
    """Valida credenciais e retorna o usuário. None se inválido."""
    user = USERS.get(email.lower().strip())
    if user and user["senha"] == senha:
        return {"email": email, **user}
    return None


def usuario_logado(request):
    """Retorna o usuário da sessão ou None."""
    return request.session.get("usuario")


def redirecionar_por_role(role: str):
    from fastapi.responses import RedirectResponse
    destinos = {"admin": "/admin", "owner": "/", "customer": "/chat"}
    return RedirectResponse(destinos.get(role, "/login"), status_code=302)
