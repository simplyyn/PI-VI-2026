USERS = {
    "admin@smartdent.com": {
        "id": "u_001",
        "nome": "Equipe SmartDent",
        "iniciais": "SD",
        "role": "admin",
        "senha": "admin123",
    },
    "dra.ana@clinicasorriso.com": {
        "id": "u_002",
        "nome": "Dra. Ana Paula",
        "iniciais": "AP",
        "role": "owner",
        "senha": "clinica123",
        "empresa": "Clínica Sorriso",
        "empresa_id": "clinica-sorriso",
        "plano": "Pro",
    },
    "joao@paciente.com": {
        "id": "u_003",
        "nome": "João Silva",
        "iniciais": "JS",
        "role": "customer",
        "senha": "paciente123",
        "empresa_id": "clinica-sorriso",
        "empresa_nome": "Clínica Sorriso",
    },
}


def autenticar(email: str, senha: str):
    user = USERS.get(email.lower().strip())
    if user and user["senha"] == senha:
        return {"email": email, **user}
    return None


def usuario_logado(request):
    return request.session.get("usuario")


def redirecionar_por_role(role: str):
    from fastapi.responses import RedirectResponse
    destinos = {"admin": "/admin", "owner": "/", "customer": "/chat"}
    return RedirectResponse(destinos.get(role, "/login"), status_code=302)
