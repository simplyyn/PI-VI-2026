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
