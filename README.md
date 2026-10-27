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

## Sprint 4 — RF004, RF005 e RF006

RF004: `analysis.AttendanceSummarizer` usa o cliente Groq existente para resumir assunto, últimas mensagens, desfecho e pendências, sem inventar resultados. `management.SummaryService` persiste um resumo por atendimento e clínica, com modelo, data e hash da versão da conversa. Não há resumo simulado. `GET /api/atendimentos/{id}/resumo` consulta o resultado; `POST` gera se ausente ou desatualizado. Conteúdo/mensagens/status alterados marcam o resumo antigo como desatualizado; a tela mostra essa condição. Resumos atualizados são reutilizados para evitar chamadas repetidas. O prompt usa até 6000 caracteres da conversa; conversas longas podem ter informações antigas fora dessa janela. O nome cadastrado não é enviado como campo, mas mensagens podem conter dados pessoais: revisar os dados antes de habilitar provedor externo.

Ao salvar um atendimento como resolvido (PUT), o backend tenta gerar o resumo automaticamente somente se `SMARTDENT_LLM_ENABLED=true`. Com o LLM desativado, mantém o atendimento salvo e informa o estado. Se o modelo falhar, o atendimento continua resolvido, o resumo anterior é preservado e a resposta contém `resumo_status=indisponivel` e mensagem do erro. O botão Resumo da IA permite nova tentativa. Não habilitamos nem fizemos chamadas reais nesta entrega.

RF005: o classificador e os endpoints existentes foram preservados. Atendimentos agora apresenta classificação individual por IA e formulário de correção manual. Relatórios oferece classificação em lote de até 10 pendentes da clínica, de todos os períodos (operação indicada no texto do botão/retorno). Alterar uma classificação atualiza os relatórios na próxima consulta. A classificação de reclamações existente não é automaticamente refeita quando a conversa muda; solicite nova classificação se necessário.

RF006: Dashboard e Relatórios usam `management.ManagementReport` e registros da clínica autenticada. `GET /api/gestao?dias=7` fornece indicadores, série por dia, reclamações por categoria e últimos atendimentos. Filtros aceitam 1 a 90 dias; a interface oferece 7, 30 e 90 dias civis, em America/Sao_Paulo. Reclamações são recortadas pela data de criação do atendimento, não pela data de classificação. Os endpoints antigos de métricas e gráficos também passaram a calcular valores reais de 7 dias. O widget flutuante consulta esses indicadores e o estoque real; suas respostas são consultas determinísticas, não geração por LLM. Satisfação/tempo de resposta aparecem como não medidos, e canal IA é descrito como valor cadastrado, não prova de automação. Atendimentos excluídos saem dos indicadores.

Persistência: SQLite usa `records.kind=summaries`; PostgreSQL usa `attendance_summaries`, criada pela migração aditiva `migrations/002_attendance_summaries.sql`, com chave estrangeira composta para isolamento e exclusão em cascata. A migração foi criada, NÃO executada nesta entrega. Atenção: o adaptador PostgreSQL existente aplica automaticamente migrações pendentes na inicialização. Revise e autorize a 002 com Guilherme antes de iniciar esta versão contra um banco PostgreSQL existente. Os testes de migração foram atualizados, mas permanecem pendentes de PostgreSQL descartável configurado.

Permissões: resumo, classificação e indicadores exigem owner; operações de escrita exigem CSRF. Nenhuma chave é enviada ao frontend. A Sugestão IA de resposta ao paciente continua separada e pendente; a Sprint 4 implementa análise/resumo e integração dos relatórios.

Para executar localmente, use o comando de Uvicorn já documentado. Não é necessário instalar dependências novas para esta etapa. Os gráficos ainda usam Chart.js via CDN; se a rede estiver indisponível, os números/tabelas renderizados pelo servidor continuam disponíveis, mas os gráficos podem não carregar.

Validação da Sprint 4 em 27/10/2026: `python -m unittest discover -s tests -v` encontrou 43 testes: 22 aprovados e 21 ignorados por dependerem de PostgreSQL descartável. Foram verificados resumo com modelo simulado, cache, desatualização, falha de geração, conclusão do atendimento apesar da falha, persistência, exclusão em cascata, isolamento, autorização e filtros de período. `node --check` validou records.js, attendance-analysis.js, management.js e 10 scripts inline extraídos das páginas renderizadas. `git diff --check` passou. Não foram executados cliques em navegador, chamadas reais de LLM ou migrações PostgreSQL.

## Demonstração com LLM e dados de teste

`seed_demo.py --clinic clinica-teste` insere apenas registros fictícios: quatro pacientes com domínio example.test, cinco itens [DEMO] e três artigos [DEMO] sobre preços de procedimentos, horários e políticas. Não sobrescreve registros existentes e não duplica os mesmos exemplos em execuções repetidas. Os preços e políticas são exemplos acadêmicos e não representam uma clínica real. O comando exige banco SQLite existente e owner na clínica informada. Nenhuma credencial é criada por esse script.

O chat de paciente e o widget flutuante agora chamam `/api/chat` para dúvidas da base; o widget continua consultando `/api/gestao` para indicadores e `/api/estoque` para estoque. As respostas mostram as fontes consultadas. Sugestão IA no atendimento preenche o campo de mensagem com uma proposta baseada no assunto: revisar antes de enviar. Não agenda, não altera estoque e não transmite mensagens a terceiros.

Para a demonstração SQLite, configure localmente `.env` (ignorado pelo Git): `SMARTDENT_DATABASE_URL=` vazio, `SMARTDENT_RETRIEVAL=local_keyword`, `SMARTDENT_LLM_ENABLED=true`, `GROQ_MODEL=openai/gpt-oss-120b` (modelo já previsto no projeto) e `GROQ_API_KEY` com sua chave pessoal. Os chats usam o mesmo provedor dos resumos e da classificação. Chave ausente/erro do provedor aparece como indisponibilidade; não há resposta simulada de sucesso. O modo local_keyword faz busca lexical, não pgvector. A busca foi normalizada para aceitar acentos opcionais e plurais simples.

O comando direto precisa carregar o arquivo:

```powershell
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

Alternativamente `npm run dev` já carrega o `.env`. Após alterar a chave, reinicie o processo (Ctrl+C e execute novamente). Nunca cole a chave no chat, frontend ou README. Não copie o `.env.example` sem ajustar os endereços PostgreSQL de exemplo, pois a demonstração local usa SQLite. Para testar, pergunte: "Qual o preço da limpeza?", "Quais os horarios de funcionamento?" ou "Qual a política de cancelamento?". Todas as informações cadastradas por seed são explicitamente fictícias.

Verificação desta integração: 46 testes encontrados, 24 aprovados e 22 ignorados por dependerem de PostgreSQL. O novo teste de seed verifica persistência, execução repetida sem duplicação e isolamento; o de chat verifica o carregamento do cliente real, sem respostas fixas. A sintaxe de ai-client.js, attendance-analysis.js e 12 scripts inline renderizados foi validada. A chamada real Groq continua não verificada: não havia chave configurada. Nenhum segredo foi exibido nem versionado.

## Provedor alternativo: Gemini (Google)

O backend agora usa `llm.create_llm()` para selecionar o cliente de acordo com `SMARTDENT_LLM_PROVIDER=gemini|groq`. O padrão sem configuração explícita continua groq para compatibilidade. O `.env` local foi configurado para gemini; os valores antigos GROQ_* ficam preservados e não são enviados quando Gemini está selecionado. Não existe fallback automático entre provedores.

Crie uma chave em https://aistudio.google.com (API keys / Create API key), confirme que o projeto tem cota gratuita e não habilite faturamento para a demonstração gratuita. Configure somente no `.env`:

```dotenv
SMARTDENT_LLM_PROVIDER=gemini
SMARTDENT_LLM_ENABLED=true
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
```

Preencha GEMINI_API_KEY no editor e reinicie o servidor com `--env-file .env` (ou npm run dev). O modelo padrão foi escolhido conforme a documentação oficial consultada; modelos/cotas podem variar por conta. Um 404 requer verificar os modelos disponíveis; 429 indica limite/cota indisponível. A integração usa REST generateContent, chave no header x-goog-api-key (nunca na URL), timeout de 20 segundos, limite de resposta e erros sanitizados, sem SDK ou dependências novas. Prompts de sistema, respostas, resumos e classificações preservam o mesmo contrato interno. O modelo utilizado fica registrado nos metadados dos resumos/classificações novos; os registros antigos não são alterados.

Documentação consultada: https://ai.google.dev/api/generate-content ; https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite ; https://ai.google.dev/gemini-api/docs/pricing . A modalidade gratuita tem cotas e pode usar conteúdo para melhoria dos produtos: use apenas dados fictícios na apresentação.

Validação: 50 testes encontrados, 28 aprovados e 22 ignorados por dependerem de PostgreSQL. Testes do cliente Gemini simulam o transporte e verificam seleção de provedor, formato da solicitação/resposta, instrução de sistema, chave fora da URL, LLM desativado, chave ausente/incompatível, HTTP 400/401/403/404/429/503, timeout, resposta vazia/bloqueada/truncada e ausência de segredos nas mensagens de erro. Nenhuma requisição real ao Gemini foi feita; ativação efetiva depende de chave válida e cota na conta. A troca não instala dependências, não executa migrações e não altera os dados de demonstração existentes.

## Pacientes integrados a Atendimentos e orçamento de exemplo

Cadastrar ou editar um paciente garante sua conversa principal, vinculada pelo ID e pela clínica, sem criar uma nova a cada atualização. O cartão do paciente tem o botão Conversa: `POST /api/pacientes/{id}/atendimento` (owner + CSRF) abre/cria o mesmo vínculo. O endereço `/atendimentos?atendimento_id=...` seleciona a conversa correspondente. A criação do vínculo é protegida por transação para evitar duplicações concorrentes. Alterar o nome do paciente atualiza o nome da conversa sem substituir assunto, mensagens ou status.

SQLite mantém o vínculo no tipo patient_links; PostgreSQL usa patient_attendance_links, descrito na migração aditiva `003_patient_attendance_links.sql` (criada, não executada nesta entrega). Ao excluir paciente, a conversa histórica é preservada e o vínculo é removido. Ao excluir a conversa, ela só é recriada em uma nova atualização do paciente ou ao clicar em Conversa. Cadastros de atendimento avulsos continuam disponíveis.

`prepare_clinic.py` foi executado no SQLite local da clinica-teste. Criou um backup consistente em data/backups antes de alterar dados; vinculou os cinco pacientes, reutilizando a conversa antiga quando havia correspondência única por nome, e criou conversas vazias para os demais. Essa associação por nome só é usada na preparação da clínica de teste; os novos cadastros usam ID. As mensagens antigas não foram removidas. O script pode ser repetido sem duplicar conversas ou o orçamento. Não executa chamadas LLM. O uso principal é a preparação local autorizada, não uma migração universal de dados reais.

Foram removidos os prefixos [DEMO] dos cinco itens de estoque e dos três títulos de artigos; os valores e o texto foram preservados. A indicação de informação fictícia continua nos conteúdos para não apresentar preços de exemplo como reais. seed_demo.py agora gera os nomes sem esse prefixo e reconhece os nomes antigos para evitar duplicação.

Na conversa de Ana Demonstração há uma solicitação de orçamento e uma resposta humana registrada como simulação: avaliação R$ 120,00 + limpeza R$ 180,00 = total estimado R$ 300,00. Os valores são lidos do artigo Preços e procedimentos e calculados com Decimal; não são preços inventados pelo modelo. Nenhum procedimento, agendamento, desconto ou envio externo foi confirmado. A tela distingue mensagens do paciente e do atendente.

Validação desta atualização: 55 testes encontrados; 31 aprovados e 24 ignorados por dependerem de PostgreSQL. Inclui criação automática, reutilização, concorrência, isolamento, atualização de nome sem perda de mensagens e preparação repetida sem duplicar orçamento. Sintaxe de records.js e git diff --check passaram. Os dados da clínica de teste foram verificados em leitura: cinco pacientes vinculados e nenhum título/nome de estoque ou artigo com o prefixo [DEMO]. Não foram executadas migrações PostgreSQL nem chamadas reais de IA nesta atualização.

## Melhorias de atendimento, agenda e orientação inicial

A área de reclamações passou a se chamar Reclamações e oportunidades de melhoria. A explicação diferencia insatisfação com a clínica de relato de dor. A revisão manual fica recolhida em details, com checkbox acessível, campos maiores, estados de foco e layout responsivo. Categoria e motivo ficam desabilitados quando não há reclamação; o envio nesse caso limpa motivo/categoria. O resultado alimenta os relatórios existentes.

O prompt do resumo agora pede um parágrafo de 2 a 4 frases, sem títulos, listas ou Markdown. Recebe o status registrado e proíbe inferir interrupção, tratamento ou conclusão clínica a partir dele. A tela limpa marcações de respostas antigas e deixa a data em informação secundária; o modelo continua salvo nos metadados da API. A versão natural-v2 invalida o cache do formato anterior, então clique em Resumo da IA para regenerar os registros existentes. Nenhuma geração real foi executada por ferramenta nesta atualização.

O catálogo catalog.py oferece 10 opções no formulário de agendamento (datalist, mantendo texto livre): avaliação, limpeza, clareamento, restauração, canal, extração, raspagem periodontal, avaliação ortodôntica, implante e prótese. O endpoint /api/procedimentos exige owner. Essas são opções de cadastro da clínica de exemplo, não uma indicação clínica nem um catálogo confirmado de outra clínica. O artigo Procedimentos disponíveis e avaliação profissional foi adicionado à base da clinica-teste; preços não cadastrados continuam dependentes de orçamento.

`enhance_clinic.py` criou quatro agendamentos fictícios para Ana, Bruno e Carla, usando a profissional Dra. Marina (exemplo), dias úteis futuros e os procedimentos de avaliação, limpeza, avaliação ortodôntica e restauração. O script verifica consultas já existentes para não duplicar esses exemplos e evita sobreposição nos horários gerados para essa profissional. O sistema geral de agenda ainda não implementa validação universal de conflitos. Um backup SQLite foi criado em data/backups antes das inserções; não houve migração PostgreSQL.

Orientação inicial: `guidance.initial_guidance`, chamada antes da recuperação RAG, reconhece alguns relatos explícitos de dor/sensibilidade/sangramento/inchaço em região odontológica e sugere consulta de avaliação, sem concluir necessidade de canal, extração ou outro tratamento. Reconhece algumas menções de dificuldade para respirar/engolir e sangramento intenso persistente para orientar pronto atendimento. Essa camada é de encaminhamento por regras, não diagnóstico, triagem clínica completa ou geração LLM: retorna gerado_por_llm=false e tipo=orientacao_inicial|orientacao_urgente. Não cobre todas as formas de linguagem, sinais de alerta ou negações. Não confirma horários, procedimentos ou preços. Outras perguntas continuam no fluxo RAG/LLM normal. A tela de atendimentos tem o botão Orientar sobre avaliação; Sugestão IA também passa pelo mesmo fluxo. As orientações gerais de encaminhamento foram baseadas em https://www.nhs.uk/symptoms/toothache/ e https://www.nhs.uk/nhs-services/dentists/how-to-find-an-nhs-dentist-in-an-emergency/ ; nenhuma recomendação de medicamento foi adicionada. Revisão profissional é necessária antes de usar o sistema com pacientes reais.

Validação: 59 testes encontrados, 34 aprovados e 25 ignorados por dependerem de PostgreSQL. Inclui orientação inicial/urgente sem chamada ao modelo, relatos com negação explícita, catálogo protegido, criação idempotente dos agendamentos e isolamento. node --check validou os arquivos JS alterados e 12 scripts inline de páginas renderizadas; git diff --check passou. Não foram testados cliques reais em navegador nem respostas reais do modelo nesta alteração.

## Conversas de exemplo e assistente de gestão ampliado

`populate_conversations.py` adicionou mensagens fictícias de cliente às conversas existentes da clinica-teste, sem apagar mensagens humanas nem duplicar os exemplos em nova execução. Todas as cinco conversas têm ao menos uma mensagem client. A conversa de Bruno Demonstração contém uma reclamação explícita sobre espera e falta de aviso, com classificação manual de exemplo na categoria tempo_espera. Não foi simulada uma resposta de IA: a origem é manual. Classificações já existentes são preservadas. Um backup local foi feito antes das alterações. As mensagens novas podem tornar os resumos antigos desatualizados; gere-os novamente quando necessário.

O widget passou a usar `POST /api/assistente` (owner + CSRF), com pergunta de até 2000 caracteres e contexto opcional limitado a um tópico conhecido. `assistant.ClinicAssistant` responde consultas operacionais diretamente a partir do repositório da clínica: agenda hoje/amanhã/próximos 7 dias, estoque e reposição, pacientes por nome/status, atendimentos por status, resumos atualizados/pendentes, reclamações e balanço de 7 dias. Perguntas da base são encaminhadas ao agente RAG/LLM existente; orientações iniciais seguem suas regras de segurança. Os dados operacionais consultados não são enviados ao modelo para gerar esses resumos numéricos.

A interface tem 13 sugestões em Rotina, Gestão e Clínica, respostas com origem identificada, links internos para a tela correspondente, atalhos permanentes, botão de limpar apenas a conversa visual e bloqueio de envio duplicado enquanto aguarda resposta. Reconhece algumas continuações simples: depois de agenda, E amanhã?; depois de pacientes, E os ativos?; depois de estoque, E os esgotados?. Esse contexto é só um tópico na página atual: não representa memória clínica nem histórico completo enviado ao modelo. A interpretação usa regras explícitas; mensagens não reconhecidas podem precisar de reformulação. Não há filtros clínicos de pacientes por sintomas, diagnóstico ou prontuário.

Pedidos para cadastrar, excluir ou alterar dados recebem um link para conferir o formulário, sem executar a alteração. As respostas distinguem conversas cadastradas de consultas realizadas; o assistente não confirma horários nem tratamentos. Os links das respostas são limitados às telas internas conhecidas e textos são inseridos com textContent. O texto IA treinada para sua clínica foi substituído para não sugerir treinamento de modelo que não foi feito.

Validação: suíte com 62 testes, 36 aprovados e 26 ignorados por dependerem de PostgreSQL. Testes adicionais verificam histórico preservado, mensagem de cliente em todas as conversas de exemplo, repetição sem duplicatas, classificação manual, consultas sem chamar modelo, fallback RAG com transporte simulado, contexto de continuação, bloqueio de escrita por mensagem, CSRF, perfil e isolamento entre clínicas. Também foram validados ai-client.js e 12 scripts inline renderizados. Não foram feitos cliques reais em navegador nem chamadas reais ao Gemini nesta atualização.

## Correção das sugestões de resposta ao cliente

O botão Sugestão IA usava somente o assunto do atendimento (por exemplo, Conversa do paciente), ignorando a pergunta que aparecia no histórico. Agora chama `POST /api/atendimentos/{id}/sugestao`, autenticado como owner e protegido por CSRF. O backend consulta o atendimento da clínica e seleciona a última mensagem client, mesmo que haja uma mensagem humana posterior; utiliza o assunto apenas quando não há mensagem de cliente. O histórico recente enviado ao agente é limitado a oito mensagens de até 1000 caracteres, com teto de 6000 caracteres, sem o nome cadastrado como campo separado. Mensagens podem conter dados pessoais: use os exemplos fictícios para apresentação.

A recuperação usa a pergunta real e expande um vocabulário limitado de atendimento (remarcar/remarcação/reagendar, horários/expediente, preço/custo/orçamento, convênios/planos). São regras lexicais locais, não uma nova busca semântica. Palavras de saudação e marcadores de exemplo deixam de pontuar a busca; termos curtos como Pix passam a ser considerados. O prompt orienta responder todas as partes documentadas de uma pergunta e identificar precisamente partes sem informação, em vez de alegar ausência total. O histórico ajuda a entender a conversa, mas não é fonte de preços ou políticas; essa autoridade continua nos artigos recuperados.

A sugestão permanece um rascunho, sem envio automático nem alteração de mensagens. Fontes ficam no aviso ao atendente, não são acrescentadas automaticamente ao texto a enviar ao cliente. Ausência de contexto é exibida como aviso, sem preencher o rascunho; edição do rascunho durante a requisição é preservada. O botão de orientação inicial também passou a usar a mensagem real persistida.

Validação: 65 testes encontrados, 38 aprovados e 27 ignorados por dependerem de PostgreSQL. O caso da pergunta sobre horários e política de remarcação foi reproduzido com LLM simulado: recuperou ambos os artigos, incluiu a última pergunta e o histórico correto, não gravou/enviou resposta e bloqueou acesso de outra clínica e perfil customer. Também foram testadas paráfrases e Pix. No banco local, a pergunta de Diego recuperou os artigos de Horários e Políticas. Sintaxe do JS e git diff --check passaram. Não foi feita chamada real ao provedor nesta correção.
