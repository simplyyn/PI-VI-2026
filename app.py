from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from auth import autenticar, usuario_logado, redirecionar_por_role

app = FastAPI(title="SmartDent AI")
app.add_middleware(SessionMiddleware, secret_key="smartdent-dev-secret-2026")
app.mount("/static", StaticFiles(directory="front"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Mock Data ────────────────────────────────────────────────────────────────

atendimentos = [
    {"id": 1, "cliente": "Maria Santos",    "iniciais": "MS", "preview": "Quero agendar uma consulta de rotina",       "status": "resolved",  "canal": "ai",    "hora": "09:15", "cor": ""},
    {"id": 2, "cliente": "Carlos Oliveira", "iniciais": "CO", "preview": "Tenho dor de dente forte desde ontem",       "status": "escalated", "canal": "human", "hora": "09:45", "cor": "red"},
    {"id": 3, "cliente": "Ana Costa",       "iniciais": "AC", "preview": "Quanto custa um clareamento dental?",        "status": "resolved",  "canal": "ai",    "hora": "10:20", "cor": ""},
    {"id": 4, "cliente": "Pedro Lima",      "iniciais": "PL", "preview": "Preciso remarcar minha consulta de amanhã", "status": "pending",   "canal": "human", "hora": "10:55", "cor": "orange"},
    {"id": 5, "cliente": "Julia Ferreira",  "iniciais": "JF", "preview": "Vocês atendem pelo plano Unimed?",           "status": "resolved",  "canal": "ai",    "hora": "11:30", "cor": ""},
    {"id": 6, "cliente": "Roberto Mendes",  "iniciais": "RM", "preview": "Quero informações sobre implantes",          "status": "pending",   "canal": "ai",    "hora": "11:50", "cor": ""},
]

metricas = {
    "atendimentos_semana": 87,
    "taxa_automatizacao": 91,
    "total_hoje": 12,
    "tempo_resposta": "18s",
    "consultas_mes": 214,
    "satisfacao": 4.8,
}

artigos_kb = [
    {"id": 1, "titulo": "Consulta de Avaliação Inicial",     "categoria": "Procedimentos", "status": True,  "views": 67,  "atualizado": "22/09/2026"},
    {"id": 2, "titulo": "Clareamento Dental — Tipos e Preços","categoria": "Estética",     "status": True,  "views": 112, "atualizado": "20/09/2026"},
    {"id": 3, "titulo": "Implante Dentário — O que esperar", "categoria": "Cirurgia",      "status": True,  "views": 89,  "atualizado": "18/09/2026"},
    {"id": 4, "titulo": "Planos de Saúde Aceitos",           "categoria": "Financeiro",    "status": True,  "views": 143, "atualizado": "15/09/2026"},
    {"id": 5, "titulo": "Tratamento de Canal — Sintomas",    "categoria": "Procedimentos", "status": True,  "views": 55,  "atualizado": "12/09/2026"},
    {"id": 6, "titulo": "Ortodontia — Aparelhos Disponíveis","categoria": "Ortodontia",    "status": True,  "views": 78,  "atualizado": "10/09/2026"},
    {"id": 7, "titulo": "Cuidados Pós-Procedimento",         "categoria": "Orientações",   "status": True,  "views": 34,  "atualizado": "08/09/2026"},
]

dados_grafico = {
    "labels":  ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
    "ia":      [12, 15, 19, 14, 18, 8, 0],
    "humano":  [3,  2,  4,  3,  3,  2,  0],
    "topicos": {
        "labels":  ["Agendamento", "Clareamento", "Implante", "Planos de Saúde", "Canal", "Ortodontia"],
        "valores": [43, 28, 22, 38, 17, 21],
    },
}

pacientes = [
    {"id": 1,  "nome": "Maria Santos",    "iniciais": "MS", "cor": "#0284c7", "telefone": "(11) 98765-4321", "email": "maria@email.com",    "ultima_consulta": "22/09/2026", "proxima_consulta": "15/10/2026", "status": "ativo",   "plano": "Unimed",       "procedimentos": 8},
    {"id": 2,  "nome": "Carlos Oliveira", "iniciais": "CO", "cor": "#059669", "telefone": "(11) 97654-3210", "email": "carlos@email.com",   "ultima_consulta": "10/09/2026", "proxima_consulta": "08/10/2026", "status": "ativo",   "plano": "Bradesco",     "procedimentos": 3},
    {"id": 3,  "nome": "Ana Costa",       "iniciais": "AC", "cor": "#7c3aed", "telefone": "(11) 96543-2109", "email": "ana@email.com",      "ultima_consulta": "05/10/2026", "proxima_consulta": "19/10/2026", "status": "novo",    "plano": "Particular",   "procedimentos": 1},
    {"id": 4,  "nome": "Pedro Lima",      "iniciais": "PL", "cor": "#d97706", "telefone": "(11) 95432-1098", "email": "pedro@email.com",    "ultima_consulta": "18/08/2026", "proxima_consulta": None,          "status": "inativo", "plano": "SulAmérica",   "procedimentos": 12},
    {"id": 5,  "nome": "Julia Ferreira",  "iniciais": "JF", "cor": "#0284c7", "telefone": "(11) 94321-0987", "email": "julia@email.com",    "ultima_consulta": "01/10/2026", "proxima_consulta": "20/10/2026", "status": "ativo",   "plano": "Unimed",       "procedimentos": 5},
    {"id": 6,  "nome": "Roberto Mendes",  "iniciais": "RM", "cor": "#dc2626", "telefone": "(11) 93210-9876", "email": "roberto@email.com",  "ultima_consulta": "29/09/2026", "proxima_consulta": "06/10/2026", "status": "ativo",   "plano": "Amil",         "procedimentos": 6},
    {"id": 7,  "nome": "Fernanda Rocha",  "iniciais": "FR", "cor": "#059669", "telefone": "(11) 92109-8765", "email": "fernanda@email.com", "ultima_consulta": "03/10/2026", "proxima_consulta": "10/10/2026", "status": "novo",    "plano": "Particular",   "procedimentos": 2},
    {"id": 8,  "nome": "Diego Alves",     "iniciais": "DA", "cor": "#7c3aed", "telefone": "(11) 91098-7654", "email": "diego@email.com",    "ultima_consulta": "12/09/2026", "proxima_consulta": "14/10/2026", "status": "ativo",   "plano": "Bradesco",     "procedimentos": 9},
    {"id": 9,  "nome": "Camila Torres",   "iniciais": "CT", "cor": "#0284c7", "telefone": "(11) 90987-6543", "email": "camila@email.com",   "ultima_consulta": "20/07/2026", "proxima_consulta": None,          "status": "inativo", "plano": "Unimed",       "procedimentos": 4},
    {"id": 10, "nome": "Lucas Barbosa",   "iniciais": "LB", "cor": "#d97706", "telefone": "(11) 89876-5432", "email": "lucas@email.com",    "ultima_consulta": "04/10/2026", "proxima_consulta": "21/10/2026", "status": "novo",    "plano": "Particular",   "procedimentos": 1},
]

agendamentos = [
    {"id": 1,  "paciente": "Maria Santos",    "horario": "08:30", "duracao": 60,  "procedimento": "Consulta de Rotina + Profilaxia",   "dentista": "Dra. Ana Paula",  "status": "confirmado", "dia": "hoje",   "cor": "#0284c7"},
    {"id": 2,  "paciente": "Carlos Oliveira", "horario": "09:30", "duracao": 90,  "procedimento": "Tratamento de Canal",               "dentista": "Dr. Carlos Melo", "status": "confirmado", "dia": "hoje",   "cor": "#059669"},
    {"id": 3,  "paciente": "Ana Costa",       "horario": "10:30", "duracao": 45,  "procedimento": "Avaliação Inicial",                 "dentista": "Dra. Ana Paula",  "status": "confirmado", "dia": "hoje",   "cor": "#7c3aed"},
    {"id": 4,  "paciente": "Pedro Lima",      "horario": "11:30", "duracao": 60,  "procedimento": "Clareamento Dental",                "dentista": "Dra. Patrícia",   "status": "pendente",   "dia": "hoje",   "cor": "#d97706"},
    {"id": 5,  "paciente": "Julia Ferreira",  "horario": "13:00", "duracao": 30,  "procedimento": "Retorno — Ortodontia",              "dentista": "Dra. Ana Paula",  "status": "confirmado", "dia": "hoje",   "cor": "#0284c7"},
    {"id": 6,  "paciente": "Roberto Mendes",  "horario": "14:00", "duracao": 120, "procedimento": "Implante Dentário — 1ª etapa",      "dentista": "Dr. Carlos Melo", "status": "confirmado", "dia": "hoje",   "cor": "#dc2626"},
    {"id": 7,  "paciente": "Fernanda Rocha",  "horario": "15:30", "duracao": 45,  "procedimento": "Consulta de Avaliação",             "dentista": "Dra. Ana Paula",  "status": "pendente",   "dia": "hoje",   "cor": "#059669"},
    {"id": 8,  "paciente": "Diego Alves",     "horario": "09:00", "duracao": 60,  "procedimento": "Restauração — Resina Composta",     "dentista": "Dra. Patrícia",   "status": "confirmado", "dia": "amanha", "cor": "#7c3aed"},
    {"id": 9,  "paciente": "Lucas Barbosa",   "horario": "10:00", "duracao": 60,  "procedimento": "Consulta de Rotina",                "dentista": "Dra. Ana Paula",  "status": "pendente",   "dia": "amanha", "cor": "#d97706"},
    {"id": 10, "paciente": "Maria Santos",    "horario": "14:00", "duracao": 45,  "procedimento": "Retorno — Clareamento",             "dentista": "Dra. Patrícia",   "status": "confirmado", "dia": "amanha", "cor": "#0284c7"},
]

clinicas = [
    {"id": "clinica-sorriso",  "nome": "Clínica Sorriso",       "plano": "Pro",        "status": "ativo",   "atendimentos_mes": 214,  "suporte": False, "owner": "dra.ana@clinicasorriso.com"},
    {"id": "odonto-center",    "nome": "OdontoCenter SP",        "plano": "Enterprise", "status": "ativo",   "atendimentos_mes": 892,  "suporte": True,  "owner": "contato@odontocenter.com"},
    {"id": "sorriso-kids",     "nome": "Sorriso Kids",           "plano": "Básico",     "status": "ativo",   "atendimentos_mes": 67,   "suporte": False, "owner": "contato@sorrisokids.com"},
    {"id": "clinica-smile",    "nome": "Clínica Smile Premium",  "plano": "Pro",        "status": "inativo", "atendimentos_mes": 0,    "suporte": False, "owner": "smile@premium.com"},
]

estoque = [
    {"id": 1,  "nome": "Luvas de Procedimento (M)",    "categoria": "EPI",          "unidade": "Caixa (100 un)", "quantidade": 8,  "minimo": 5,  "status": "ok"},
    {"id": 2,  "nome": "Anestésico Articaína 4%",      "categoria": "Anestésicos",  "unidade": "Caixa (50 un)",  "quantidade": 2,  "minimo": 3,  "status": "baixo"},
    {"id": 3,  "nome": "Brocas Diamantadas Esféricas", "categoria": "Instrumental", "unidade": "Kit (10 un)",    "quantidade": 0,  "minimo": 2,  "status": "esgotado"},
    {"id": 4,  "nome": "Resina Composta A2",           "categoria": "Restauração",  "unidade": "Seringa 4g",     "quantidade": 12, "minimo": 6,  "status": "ok"},
    {"id": 5,  "nome": "Fio Retrator #000",            "categoria": "Protética",    "unidade": "Rolo",           "quantidade": 3,  "minimo": 2,  "status": "ok"},
    {"id": 6,  "nome": "Alginato (500g)",              "categoria": "Moldagem",     "unidade": "Pote",           "quantidade": 1,  "minimo": 3,  "status": "baixo"},
    {"id": 7,  "nome": "Papel Articular 40μm",         "categoria": "Diagnóstico",  "unidade": "Bloco",          "quantidade": 5,  "minimo": 2,  "status": "ok"},
    {"id": 8,  "nome": "Máscaras Cirúrgicas",          "categoria": "EPI",          "unidade": "Caixa (50 un)",  "quantidade": 15, "minimo": 10, "status": "ok"},
    {"id": 9,  "nome": "Hipoclorito de Sódio 2,5%",   "categoria": "Endodontia",   "unidade": "Frasco 500ml",   "quantidade": 4,  "minimo": 3,  "status": "ok"},
    {"id": 10, "nome": "Lima Endodôntica #15",         "categoria": "Endodontia",   "unidade": "Caixa (6 un)",   "quantidade": 1,  "minimo": 4,  "status": "baixo"},
]

# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if usuario_logado(request):
        return redirecionar_por_role(usuario_logado(request)["role"])
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), senha: str = Form(...)):
    user = autenticar(email, senha)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": "E-mail ou senha incorretos.",
            "email": email,
        })
    request.session["usuario"] = {
        "id":           user["id"],
        "nome":         user["nome"],
        "iniciais":     user["iniciais"],
        "role":         user["role"],
        "email":        email,
        "empresa":      user.get("empresa", "SmartDent"),
        "empresa_id":   user.get("empresa_id", ""),
        "empresa_nome": user.get("empresa_nome", ""),
        "plano":        user.get("plano", ""),
    }
    return redirecionar_por_role(user["role"])

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ─── Owner Routes ─────────────────────────────────────────────────────────────

def _owner_ctx(request, extra: dict = {}):
    user = usuario_logado(request)
    if not user or user["role"] != "owner":
        return None
    return {"request": request, "usuario": user, **extra}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = _owner_ctx(request, {"pagina": "dashboard", "metricas": metricas, "atendimentos": atendimentos[:3]})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("index.html", ctx)

@app.get("/atendimentos", response_class=HTMLResponse)
async def pagina_atendimentos(request: Request):
    ctx = _owner_ctx(request, {"pagina": "atendimentos", "atendimentos": atendimentos})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("atendimentos.html", ctx)

@app.get("/base-conhecimento", response_class=HTMLResponse)
async def pagina_conhecimento(request: Request):
    ctx = _owner_ctx(request, {"pagina": "conhecimento", "artigos": artigos_kb})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("conhecimento.html", ctx)

@app.get("/relatorios", response_class=HTMLResponse)
async def pagina_relatorios(request: Request):
    ctx = _owner_ctx(request, {"pagina": "relatorios", "metricas": metricas, "grafico": dados_grafico})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("relatorios.html", ctx)

@app.get("/configuracoes", response_class=HTMLResponse)
async def pagina_configuracoes(request: Request):
    ctx = _owner_ctx(request, {"pagina": "configuracoes"})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("configuracoes.html", ctx)

@app.get("/pacientes", response_class=HTMLResponse)
async def pagina_pacientes(request: Request):
    ctx = _owner_ctx(request, {"pagina": "pacientes", "pacientes": pacientes})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("pacientes.html", ctx)

@app.get("/agendamentos", response_class=HTMLResponse)
async def pagina_agendamentos(request: Request):
    total = len(agendamentos)
    ctx = _owner_ctx(request, {"pagina": "agendamentos", "agendamentos": agendamentos, "total": total})
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("agendamentos.html", ctx)

@app.get("/estoque", response_class=HTMLResponse)
async def pagina_estoque(request: Request):
    total     = len(estoque)
    baixo     = sum(1 for i in estoque if i["status"] == "baixo")
    esgotado  = sum(1 for i in estoque if i["status"] == "esgotado")
    ctx = _owner_ctx(request, {
        "pagina": "estoque",
        "estoque": estoque,
        "total": total,
        "baixo": baixo,
        "esgotado": esgotado,
    })
    if ctx is None:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("estoque.html", ctx)

# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_painel(request: Request):
    user = usuario_logado(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("admin.html", {
        "request": request, "usuario": user, "clinicas": clinicas,
    })

# ─── Customer Routes ──────────────────────────────────────────────────────────

@app.get("/chat", response_class=HTMLResponse)
async def chat_cliente(request: Request):
    user = usuario_logado(request)
    if not user or user["role"] != "customer":
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("chat.html", {
        "request": request, "usuario": user,
    })

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.get("/api/atendimentos")
async def api_atendimentos():
    return atendimentos

@app.get("/api/metricas")
async def api_metricas():
    return metricas

@app.get("/api/base-conhecimento")
async def api_conhecimento():
    return artigos_kb

@app.get("/api/relatorios/grafico")
async def api_grafico():
    return dados_grafico

@app.get("/api/estoque")
async def api_estoque():
    return estoque
