# PI-VI-2026
# Projeto Integrador 6
# O projeto propõe o desenvolvimento de um assistente inteligente para pequenos negócios, com o objetivo de automatizar o atendimento ao cliente e apoiar a gestão diária da empresa por meio de Inteligência Artificial. A solução permite que o próprio negócio cadastre informações sobre produtos, serviços, preços e políticas de funcionamento, formando uma base de conhecimento personalizada que alimenta a IA. A partir dela, o sistema responde dúvidas de clientes, sugere respostas para mensagens, resume atendimentos, identifica motivos recorrentes de reclamações e gera relatórios gerenciais. A metodologia adotada é o SCRUM, com desenvolvimento incremental em sprints. Como resultado esperado, pretende-se entregar uma plataforma web funcional, capaz de oferecer respostas personalizadas e confiáveis, baseadas exclusivamente nos dados fornecidos por cada empresa.

## Backend das Sprints 2 a 4

O banco definitivo é PostgreSQL com pgvector (`postgres.py` + `migrations/`), usado sempre que `SMARTDENT_DATABASE_URL` está definido e obrigatório em produção. Sem a URL, a aplicação usa o SQLite provisório (`persistence.py`), mantido só como fallback de desenvolvimento para quem não tem PostgreSQL; a busca semântica existe apenas no PostgreSQL. Os adaptadores concentram SQL; `services.py` contém validação e regras sem SQL. Os dois preservam o mesmo contrato do repositório (user, user_by_id, add_user, list, save, delete, move, append_message, set_complaint, delete_complaint), verificado pela mesma suíte de testes nos dois bancos.

### Executar (Python 3.12)

Atalho (Node 18+, sem dependências npm): com o venv criado e as dependências instaladas, `npm run dev` sobe o servidor com reload automático em http://127.0.0.1:8000, `npm test` roda a suíte, e `npm run manage -- <comando>` executa o manage.py no mesmo banco (ex.: `npm run manage -- create-user --email ...`; rodar `python manage.py` direto ignora o `.env`). O `scripts/dev.mjs` procura o Python em `SMARTDENT_PYTHON`, `.venv` ou `~/.venvs/smartdent`, lê um `.env` local (copie de `.env.example`; variáveis do terminal têm prioridade) e usa `SMARTDENT_ENV=development`. Ele também gera um segredo de sessão fixo durante a execução, para o login não cair a cada reload. Sem `SMARTDENT_DATABASE_URL` no `.env`, usa o SQLite. Passo a passo manual:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
$env:SMARTDENT_ENV = 'development'
# PostgreSQL (definitivo): por exemplo, com Docker. Sem esta variável, usa o SQLite abaixo.
$env:SMARTDENT_DB_PASSWORD = '<senha forte local>'
docker compose up -d
$env:SMARTDENT_DATABASE_URL = "postgresql://smartdent:$($env:SMARTDENT_DB_PASSWORD)@127.0.0.1:5432/smartdent"
.venv/Scripts/python.exe manage.py migrate
$env:SMARTDENT_DB_PATH = 'data/smartdent.sqlite3'
# Opcional no desenvolvimento: chave aleatória estável para manter sessões entre reinícios.
$env:SMARTDENT_SESSION_SECRET = (& .venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
.venv/Scripts/python.exe manage.py create-user --email owner@example.test --nome 'Responsável de Teste' --role owner --clinic clinica-teste
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

A senha é solicitada no terminal, nunca como argumento. Para paciente, crie outro usuário com role customer e a mesma clinic; para administrador, role admin. Não há contas padrão. No PostgreSQL, `--clinic-nome 'Clínica Teste'` define o nome exibido ao criar a clínica. O banco é criado de forma aditiva na inicialização/provisionamento (as migrações pendentes rodam ao iniciar), sem importar usuários ou dados fictícios antigos. O SQLite provisório usa usuários e registros JSON particionados por tipo e clínica; dados de um SQLite antigo não são migrados para o PostgreSQL.

`.env.example` documenta variáveis. A aplicação NÃO carrega `.env` automaticamente; só os atalhos `npm run dev`/`npm test` o leem, para desenvolvimento. Fora deles, configure as variáveis no processo PowerShell. Em produção, `SMARTDENT_ENV=production`, segredo obrigatório com ao menos 32 caracteres e HTTPS; o cookie será Secure, HttpOnly e SameSite Strict. No desenvolvimento, sem segredo configurado, um valor aleatório é gerado por processo e sessões expiram após reinício; use um único worker ou configure um segredo estável.

### APIs para Caio

Acesse `/docs` após login. O formulário de login também exige CSRF (obtido por GET /login). `GET /api/session` fornece usuário e token CSRF; envie o token em `X-CSRF-Token` nas operações de escrita e logout. O ID da clínica vem da sessão/usuário no servidor; não é aceito no payload.

- `GET/POST /api/base-conhecimento`; `PUT/DELETE /api/base-conhecimento/{id}`. Payload de criação/edição: titulo, categoria, conteudo, status (booleano, padrão true). conteudo é o texto usado na recuperação: no PostgreSQL ele é dividido em trechos e indexado no pgvector a cada criação/edição. views e atualizado são mantidos pelo backend.
- `GET/POST /api/estoque`; `PUT/DELETE /api/estoque/{id}`. Payload: nome, categoria, unidade, quantidade e minimo (inteiros não negativos).
- `POST /api/estoque/{id}/movimentacoes`: `{"delta": 2}` para entrada ou valor negativo para saída. Rejeita saldo negativo e movimentação zero. A transação (SELECT ... FOR UPDATE no PostgreSQL, BEGIN IMMEDIATE no SQLite) evita perda de atualização. No PostgreSQL cada movimentação fica registrada em `stock_movements` (delta e saldo); ainda não há endpoint de consulta desse histórico.
- `POST /logout`: exige token CSRF. Links existentes usam `front/session.js` para encerrar a sessão.
- CRUD exige perfil owner; customer só acessa chat; admin acessa o painel administrativo. Provisionamento de usuários é local via manage.py, sem endpoint público de cadastro.

As páginas de conhecimento/estoque leem dados persistidos. Os botões estão conectados via front/crud.js: formulários de cadastro/edição, exclusão com confirmação, movimentação de estoque e ativação de artigos. Busca por texto e categorias funcionam localmente sobre a lista carregada. As operações usam sessão e token CSRF; erros aparecem na tela e os dados são recarregados após salvar. As demais telas e chats JavaScript existentes continuam demonstrativos. Os dados fixos antigos não foram importados. Métricas e o painel administrativo continuam demonstrativos. Pacientes, agendamentos e atendimentos agora usam registros persistidos por clínica; o dashboard ainda precisa ser alinhado a essas novas fontes.

### LLM e agente

`llm.py` implementa Groq Chat Completions com urllib (sem SDK adicional), timeout de 20s, resposta limitada e erros sanitizados. Referência oficial: https://console.groq.com/docs/api-reference . Configure GROQ_API_KEY e GROQ_MODEL apenas no servidor; não há chave no frontend. SMARTDENT_LLM_ENABLED=false por padrão: nenhuma chamada ao modelo. Habilitar true exige autorização e pode gerar custos. Nenhuma chamada real foi feita durante a implementação.

`POST /api/chat`, payload `{"pergunta":"..."}`, aceita owner/customer e exige CSRF. Retorna resposta, fontes candidatas e gerado_por_llm. `SMARTDENT_RETRIEVAL` vazio escolhe automaticamente: `pgvector` com PostgreSQL e `pending` com SQLite. `pgvector` é a busca semântica híbrida descrita abaixo; `pending` retorna 503; `local_keyword` recupera artigos ativos por palavras em Python (lexical, funciona nos dois bancos). Sem contexto, retorna falta de dados sem chamar LLM. Com contexto e LLM desativado, retorna 503. Não há resposta artificial de sucesso.

`rag.Retriever.retrieve(clinic, question, limit=4)` é o contrato Python interno: retorna documentos já filtrados pela clínica, com id, titulo, conteudo e status; empresa_id opcional deve corresponder à clínica. `rag.PgVectorRetriever` o implementa no próprio processo (sem serviço HTTP externo) e é o mesmo usado por `GET /api/base-conhecimento/busca`. O prompt restringe informações e trata documentos como dados, mas não garante que um modelo nunca alucine. As fontes são documentos enviados ao modelo, não prova automática de cada afirmação. O chat visual ainda depende de Caio.

### PostgreSQL/pgvector — modelo de dados (Sprint 2)

`migrations/001_schema.sql` define o MER. Cada arquivo de `migrations/` roda uma única vez, em transação, registrado em `schema_migrations` e protegido por advisory lock (vários workers podem iniciar juntos). Requer PostgreSQL 14+ com pgvector 0.5+ (`docker-compose.yml` usa a imagem `pgvector/pgvector:0.8.0-pg17`, só em 127.0.0.1). O pgvector não é uma extensão "trusted": se o usuário da aplicação não for superusuário, crie-a antes como superusuário em cada banco (`CREATE EXTENSION vector;`), e a migração apenas a encontra. No Windows com o instalador oficial, o pgvector não vem incluído: compile com Visual Studio Build Tools (C++) e `nmake /F Makefile.win` seguindo o README do pgvector.

| Entidade (PDF) | Tabela | Observações |
|---|---|---|
| Clínica | `clinics` | id textual (o `--clinic` do manage.py), nome, plano, status |
| Usuário | `users` | e-mail único em minúsculas, perfil admin/owner/customer, clínica obrigatória exceto admin |
| Procedimento, Convênio, Política/FAQ | `kb_articles` | artigos categorizados, como a tela atual; coluna `busca` (tsvector em português) gerada |
| (embeddings) | `kb_chunks` | trechos de ~500 caracteres, `vector(384)`, índice HNSW por cosseno, modelo registrado |
| Paciente | `patients` | |
| Agendamento | `appointments` | FK composta (clínica, paciente): impede vincular paciente de outra clínica |
| Conversa/Atendimento | `attendances` | |
| Mensagem | `attendance_messages` | uma linha por mensagem |
| Reclamação | `complaint_classifications` | no máximo uma por atendimento; ver Sprint 4 |
| Insumo e movimentação | `stock_items`, `stock_movements` | quantidade 0..1e9 garantida por CHECK |
| Relatório/Métrica | (consultas) | calculados sob demanda, não armazenados |

Isolamento: toda consulta filtra por `clinic_id`, e as chaves estrangeiras compostas `(clinic_id, id)` garantem no banco que agendamentos, mensagens, trechos, movimentações e reclamações só apontam para registros da mesma clínica. Excluir artigo, atendimento ou insumo remove em cascata seus trechos, mensagens, classificação e histórico; excluir paciente com agendamentos é bloqueado (RESTRICT). Os nomes de colunas seguem os campos da API, e as datas saem nos mesmos formatos do SQLite, sem mudança para o frontend.

### Busca semântica — endpoint pgvector (Sprint 3)

- Embeddings locais com fastembed (ONNX) e o modelo multilíngue `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões): sem chave, sem custo e sem enviar textos para fora do servidor. Na primeira utilização o modelo (~220 MB) é baixado do Hugging Face para `FASTEMBED_CACHE_PATH`; o carregamento inicial leva dezenas de segundos e depois cada texto leva poucos milissegundos em CPU. `SMARTDENT_EMBEDDINGS=off` desativa (a busca pgvector passa a responder 503).
- Indexação: criar/editar artigo divide `titulo + conteudo` em trechos e grava os embeddings na mesma transação do artigo. Alterar só status/categoria não recalcula. Se o modelo falhar, o artigo é salvo sem índice e um aviso vai para o log; `manage.py reindex` indexa os pendentes, e `manage.py reindex --todos` refaz tudo (use após trocar `SMARTDENT_EMBEDDING_MODEL`; outro modelo precisa gerar 384 dimensões ou uma nova migração).
- Consulta híbrida: os 24 trechos mais próximos por cosseno (`<=>`) da clínica, apenas de artigos ativos, mais busca textual em português (`websearch_to_tsquery`), combinados por Reciprocal Rank Fusion. Trechos com distância acima de `SMARTDENT_RETRIEVAL_MAX_DISTANCE` (padrão 0.7) são descartados: perguntas fora do assunto ficam sem contexto e não chamam o LLM. A parte textual recupera nomes próprios que o vetor aproxima mal (ex.: "Unimed"). Artigos longos enviam ao agente só os trechos relevantes.
- `GET /api/base-conhecimento/busca?q=texto&limite=5` (owner; RF007 consulta rápida): `[{"id", "titulo", "categoria", "trecho", "score", "distancia"}]`, ordenado por relevância. `distancia` é null quando o artigo veio só da busca textual; com `local_keyword` não há score. 503 com busca desativada ou modelo indisponível.

Calibração do limiar (14/10/2026, modelo real, 7 artigos fictícios): perguntas relevantes ficaram entre 0,26 e 0,69 de distância, e paráfrases como "desmarcar" contra "cancelamento" ficaram perto de 0,69. Perguntas fora do assunto ficaram de 0,57 a 1,02. Com 0,7, todas as relevantes trouxeram o artigo certo em 1º lugar; 3 de 5 irrelevantes ficaram sem contexto e as outras 2 trouxeram um documento inócuo, que o prompt manda ignorar. Reavalie o limiar com a base real da clínica parceira.

### Reclamações — RF005 (Sprint 4)

`analysis.py` é o Agente de Análise/Gestão (o RF004, resumo, pode ser adicionado no mesmo módulo). O classificador envia ao mesmo LLM (`llm.GroqClient`) o assunto e as últimas mensagens do atendimento, **sem o nome do paciente**, e exige JSON com `reclamacao`, `categoria` (lista fixa) e `motivo`. A resposta é validada; formato inválido retorna 503 e nada é salvo. Com `SMARTDENT_LLM_ENABLED=false` não há chamada nem classificação simulada (503). O responsável pode classificar ou corrigir manualmente, o que também alimenta os relatórios sem LLM. Atendimentos analisados sem reclamação ficam registrados para não serem reenviados ao modelo.

Categorias (`GET /api/reclamacoes/categorias`): agendamento, tempo_espera, atendimento, preco_pagamento, convenio, procedimento, infraestrutura, outros.

Endpoints (owner; CSRF nas escritas):

- `POST /api/atendimentos/{id}/reclamacao/classificar`: classifica um atendimento com o LLM.
- `POST /api/reclamacoes/classificar?limite=10`: classifica até `limite` (máximo 20) atendimentos ainda não analisados. Cada resultado é salvo assim que obtido; se o LLM falhar no meio, os já salvos permanecem e a resposta é 503 (chame de novo para continuar). Retorna `{"classificados": [...], "restantes": n}`.
- `PUT /api/atendimentos/{id}/reclamacao`: classificação manual `{"reclamacao": true, "categoria": "tempo_espera", "motivo": "..."}`. Com `reclamacao` false a categoria é ignorada.
- `DELETE /api/atendimentos/{id}/reclamacao`: remove a classificação; o atendimento volta a pendente.
- `GET /api/reclamacoes`: classificações com `origem` (ia/manual), `modelo`, `classificado_em`, `rotulo`, `cliente` e `assunto`.
- `GET /api/relatorios/reclamacoes?dias=30` (dias opcional, pela data do atendimento): dados para Relatórios e Dashboard (RF006). Resposta: `{"periodo_dias", "atendimentos", "analisados", "pendentes", "reclamacoes", "categorias": [{"categoria", "rotulo", "total", "percentual", "exemplos"}], "labels", "valores"}`. `labels`/`valores` seguem o mesmo formato de `grafico.topicos` e podem ir direto para o Chart.js da tela de Relatórios; conectar as telas é tarefa do Caio.

### Testes

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
# Também contra PostgreSQL: use um banco DESCARTÁVEL (cada teste cria e remove um schema próprio).
$env:SMARTDENT_TEST_DATABASE_URL = 'postgresql://smartdent:<senha>@127.0.0.1:5432/smartdent_testes'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Testes usam banco temporário, usuários fictícios e transporte LLM simulado. Cobrem hash/login/persistência em nova conexão, logout/CSRF/perfis, isolamento de clínicas, CRUD conhecimento, movimentação e quantidades inválidas, LLM desativado/timeout/resposta inválida/sucesso simulado, recuperação lexical e agente sem contexto. Esses arquivos não demonstram aprovação dos testes: consulte o relatório da execução. Sem `SMARTDENT_TEST_DATABASE_URL`, os testes de PostgreSQL aparecem como ignorados (skipped). Os testes pgvector usam um embedder determinístico por palavras, sem rede; o modelo real foi verificado à parte (abaixo). Chamada real Groq não foi verificada.

Windows com Controle Inteligente de Aplicativos: se `import psycopg` falhar com "Uma política de Controle de Aplicativo bloqueou este arquivo", a DLL do `psycopg[binary]` foi bloqueada. O psycopg passa a usar a implementação Python pura se encontrar a `libpq.dll` no PATH (por exemplo, a pasta `bin` de uma instalação do PostgreSQL); defina `PSYCOPG_IMPL=python` para usá-la diretamente.

Validação PostgreSQL/pgvector em 14/10/2026: PostgreSQL 16.2 + pgvector 0.6.2 locais (pacote `pgserver`, fora do projeto), Python 3.12. `unittest discover`: 37 testes aprovados com o PostgreSQL (incluindo a suíte HTTP completa repetida sobre ele, o contrato do repositório nos dois bancos, 40 movimentações de estoque concorrentes sem perda, migração idempotente, isolamento da busca, reindexação e falha do modelo). Sem a URL: 37 executados, 18 ignorados e o restante aprovado. Ponta a ponta com o modelo real (fastembed 0.9.0): API → indexação → `/api/base-conhecimento/busca` e `manage.py migrate`/`reindex` funcionaram. `docker-compose.yml` não foi executado (Docker indisponível na máquina de validação). Depois, no mesmo dia, com PostgreSQL 17.11 (instalador oficial, serviço do Windows) e pgvector 0.8.7 compilado com MSVC: 37 testes aprovados, com a busca iterativa do pgvector 0.8 ativa e a mesma calibração com o modelo real.

Limitações: sem gerenciamento de usuários pela interface, recuperação de senha, limitação de tentativas de login ou revogação individual de cookies copiados antes de logout (logout limpa o cookie do navegador; prazo máximo 8h). Essas melhorias são necessárias antes de uso público em produção.

Validação local em 13/10/2026: Python 3.12.13 e dependências instalados com autorização. `python -m unittest discover -s tests -v`: 8 testes aprovados, incluindo edição/exclusão de estoque, leitura após reabrir SQLite e endpoint de chat com modelo simulado. Nenhuma chamada real Groq, teste PostgreSQL ou busca pgvector foi executado. Há um aviso de depreciação da assinatura antiga de TemplateResponse usada pelas telas existentes; os testes passaram com esse aviso.

Validação da integração das telas: 9 testes aprovados; node --check front/crud.js e git diff --check passaram. O teste adicional verifica renderização dos controles e escaping dos artigos. Não foi possível executar cliques em navegador, pois nenhum navegador estava conectado à ferramenta disponível.

### Pacientes, agendamentos e atendimentos

Os três recursos foram conectados ao SQLite provisório, sem importar dados fictícios antigos. As telas começam vazias para cada clínica. Cadastre primeiro um paciente para agendar.

- `/api/pacientes`, `/api/agendamentos`, `/api/atendimentos`: GET/POST; PUT/DELETE em `/{id}`, sempre owner, sessão e CSRF nas escritas.
- Paciente preserva nome, telefone, email, status, plano, datas de consultas e quantidade de procedimentos. Iniciais e cor são gerados; datas são ISO (AAAA-MM-DD), opcionais. As datas e a contagem de procedimentos do paciente são campos manuais; não são atualizadas automaticamente por agendamentos.
- Agendamento usa paciente_id da mesma clínica, data real, horario, duracao, procedimento, dentista e status. Confirmar e cancelar atualizam status; excluir remove o registro. Não há catálogo de profissionais, validação de disponibilidade ou bloqueio de sobreposição de horários ainda. Pacientes com agendamentos não podem ser excluídos antes de remover esses vínculos; podem ser marcados inativos.
- Atendimento preserva cliente, preview (assunto), status e canal. Mensagens humanas ficam salvas atomicamente em `/api/atendimentos/{id}/mensagens`; editar dados do atendimento preserva suas mensagens. Marcar canal como ai não executa modelo. Resumo/sugestão IA mostram a dependência existente; nenhuma geração simulada foi introduzida.
- Tela de pacientes: novo/editar/excluir, exportação JSON local, histórico de agendamentos registrados e botão Agendar com paciente pré-selecionado.
- Tela de agendamentos: novo/editar/excluir, confirmar/cancelar, filtros por texto/status/data e calendário navegável construído com datas locais do navegador.
- Tela de atendimentos: novo/editar/excluir, selecionar conversa, registrar mensagem humana, escalar e resolver. Mensagens ficam somente no sistema: nenhuma comunicação externa foi enviada.

No SQLite provisório os três ficam no adaptador records (tipos patients, appointments e attendance). No PostgreSQL usam as tabelas `patients`, `appointments` (paciente_id com FK da mesma clínica, data/horário tipados) e `attendances` + `attendance_messages`, com os mesmos campos da API.

Validação: 10 testes locais, incluindo CRUD dos três recursos, vínculo de paciente da mesma clínica, restrição de exclusão, mensagens preservadas, autorização e isolamento, validações de data/duração/status e renderização das telas. Sintaxe de records.js validada com Node. Cliques reais em navegador não foram verificados: não há navegador conectado disponível.
