from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from auth import autenticar, usuario_logado, redirecionar_por_role

app = FastAPI(title="SmartBiz AI")
app.add_middleware(SessionMiddleware, secret_key="smartbiz-dev-secret-2026")
app.mount("/static", StaticFiles(directory="front"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Mock Data ────────────────────────────────────────────────────────────────

atendimentos = [
    {"id": 1, "cliente": "Maria Santos",    "iniciais": "MS", "preview": "Qual o prazo de entrega para o Rio?",  "status": "resolved",  "canal": "ai",    "hora": "14:23", "cor": ""},
    {"id": 2, "cliente": "Carlos Oliveira", "iniciais": "CO", "preview": "Quero cancelar meu pedido urgente",    "status": "escalated", "canal": "human", "hora": "13:50", "cor": "red"},
    {"id": 3, "cliente": "Ana Costa",       "iniciais": "AC", "preview": "Vocês aceitam pagamento no Pix?",      "status": "resolved",  "canal": "ai",    "hora": "13:10", "cor": ""},
    {"id": 4, "cliente": "Pedro Silva",     "iniciais": "PS", "preview": "O produto chegou com defeito...",      "status": "pending",   "canal": "human", "hora": "12:45", "cor": "orange"},
    {"id": 5, "cliente": "Juliana Ferreira","iniciais": "JF", "preview": "Qual o horário de funcionamento?",     "status": "resolved",  "canal": "ai",    "hora": "11:30", "cor": ""},
    {"id": 6, "cliente": "Roberto Lima",    "iniciais": "RL", "preview": "Tem promoção para clientes antigos?",  "status": "pending",   "canal": "ai",    "hora": "10:55", "cor": ""},
]

metricas = {
    "atendimentos_semana": 142,
    "taxa_automatizacao": 94,
    "total_hoje": 34,
    "tempo_resposta": "12s",
}

artigos_kb = [
    {"id": 1, "titulo": "Prazo de Entrega por Região",       "categoria": "Logística",  "status": True,  "views": 45,  "atualizado": "20/09/2026"},
    {"id": 2, "titulo": "Formas de Pagamento Aceitas",       "categoria": "Financeiro", "status": True,  "views": 87,  "atualizado": "18/09/2026"},
    {"id": 3, "titulo": "Política de Trocas e Devoluções",   "categoria": "Pós-venda",  "status": True,  "views": 33,  "atualizado": "15/09/2026"},
    {"id": 4, "titulo": "Horários de Funcionamento",         "categoria": "Geral",      "status": True,  "views": 112, "atualizado": "10/09/2026"},
    {"id": 5, "titulo": "Tabela de Fretes Especiais",        "categoria": "Logística",  "status": False, "views": 12,  "atualizado": "05/09/2026"},
    {"id": 6, "titulo": "Cupons e Promoções Ativas",         "categoria": "Marketing",  "status": True,  "views": 68,  "atualizado": "22/09/2026"},
    {"id": 7, "titulo": "Manutenção Preventiva de Produtos", "categoria": "Pós-venda",  "status": True,  "views": 22,  "atualizado": "12/09/2026"},
]

dados_grafico = {
    "labels":  ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
    "ia":      [16, 22, 28, 20, 26, 13, 5],
    "humano":  [2,  2,  3,  2,  2,  1,  0],
    "topicos": {
        "labels":  ["Prazo entrega", "Pagamento", "Troca/Dev.", "Horário", "Frete", "Outros"],
        "valores": [34, 28, 19, 15, 12, 8],
    },
}

empresas = [
    {"id": "padaria-do-joao", "nome": "Padaria do João",   "plano": "Pro",        "status": "ativo",   "atendimentos_mes": 342,  "suporte": False, "owner": "joao@padaria.com"},
    {"id": "hospital-sp",     "nome": "Hospital São Paulo","plano": "Enterprise", "status": "ativo",   "atendimentos_mes": 1840, "suporte": True,  "owner": "hospital@sp.com"},
    {"id": "auto-center",     "nome": "Auto Center Silva", "plano": "Básico",     "status": "ativo",   "atendimentos_mes": 89,   "suporte": False, "owner": "silva@auto.com"},
    {"id": "clinica-vital",   "nome": "Clínica Vital",     "plano": "Pro",        "status": "inativo", "atendimentos_mes": 0,    "suporte": False, "owner": "vital@clinica.com"},
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
        "id":          user["id"],
        "nome":        user["nome"],
        "iniciais":    user["iniciais"],
        "role":        user["role"],
        "email":       email,
        "empresa":     user.get("empresa", "SmartBiz"),
        "empresa_id":  user.get("empresa_id", ""),
        "empresa_nome":user.get("empresa_nome", ""),
        "plano":       user.get("plano", ""),
    }
    return redirecionar_por_role(user["role"])

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ─── Owner Routes (protegidas) ────────────────────────────────────────────────

def _owner_ctx(request, extra: dict = {}):
    """Contexto base para todas as rotas do owner."""
    user = usuario_logado(request)
    if not user or user["role"] != "owner":
        return None
    return {"request": request, "usuario": user, **extra}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = _owner_ctx(request, {"pagina": "dashboard", "metricas": metricas, "atendimentos": atendimentos[:2]})
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

# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_painel(request: Request):
    user = usuario_logado(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("admin.html", {
        "request": request, "usuario": user, "empresas": empresas,
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
