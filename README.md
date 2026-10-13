# PI-VI-2026
# Projeto Integrador 6
# O projeto propõe o desenvolvimento de um assistente inteligente para pequenos negócios, com o objetivo de automatizar o atendimento ao cliente e apoiar a gestão diária da empresa por meio de Inteligência Artificial. A solução permite que o próprio negócio cadastre informações sobre produtos, serviços, preços e políticas de funcionamento, formando uma base de conhecimento personalizada que alimenta a IA. A partir dela, o sistema responde dúvidas de clientes, sugere respostas para mensagens, resume atendimentos, identifica motivos recorrentes de reclamações e gera relatórios gerenciais. A metodologia adotada é o SCRUM, com desenvolvimento incremental em sprints. Como resultado esperado, pretende-se entregar uma plataforma web funcional, capaz de oferecer respostas personalizadas e confiáveis, baseadas exclusivamente nos dados fornecidos por cada empresa.

## Backend das Sprints 2 e 3 — implementação provisória

SQLite é uma solução provisória para desenvolvimento e testes. A integração definitiva com PostgreSQL/pgvector depende do alinhamento com Guilherme. Nenhum esquema PostgreSQL foi criado. O adaptador em `persistence.py` concentra SQL; `services.py` contém validação e regras sem SQL. A futura implementação deve preservar o contrato do repositório (user, user_by_id, add_user, list, save, delete, move), incluindo isolamento e movimentação atômica.

### Executar (Python 3.12)

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
$env:SMARTDENT_ENV = 'development'
$env:SMARTDENT_DB_PATH = 'data/smartdent.sqlite3'
# Opcional no desenvolvimento: chave aleatória estável para manter sessões entre reinícios.
$env:SMARTDENT_SESSION_SECRET = (& .venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
.venv/Scripts/python.exe manage.py create-user --email owner@example.test --nome 'Responsável de Teste' --role owner --clinic clinica-teste
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

A senha é solicitada no terminal, nunca como argumento. Para paciente, crie outro usuário com role customer e a mesma clinic; para administrador, role admin. Não há contas padrão. O banco é criado de forma aditiva na inicialização/provisionamento, sem importar usuários ou dados fictícios antigos. O esquema provisório usa usuários e registros JSON particionados por tipo e clínica, sem propor o esquema definitivo da equipe.

`.env.example` documenta variáveis; a aplicação NÃO carrega `.env` automaticamente. Configure as variáveis no processo PowerShell. Em produção, `SMARTDENT_ENV=production`, segredo obrigatório com ao menos 32 caracteres e HTTPS; o cookie será Secure, HttpOnly e SameSite Strict. No desenvolvimento, sem segredo configurado, um valor aleatório é gerado por processo e sessões expiram após reinício; use um único worker ou configure um segredo estável.

### APIs para Caio

Acesse `/docs` após login. O formulário de login também exige CSRF (obtido por GET /login). `GET /api/session` fornece usuário e token CSRF; envie o token em `X-CSRF-Token` nas operações de escrita e logout. O ID da clínica vem da sessão/usuário no servidor; não é aceito no payload.

- `GET/POST /api/base-conhecimento`; `PUT/DELETE /api/base-conhecimento/{id}`. Payload de criação/edição: titulo, categoria, conteudo, status (booleano, padrão true). conteudo é o novo texto necessário para recuperação, ausente nos mocks antigos; alinhar seu armazenamento com Guilherme. views e atualizado são mantidos pelo backend.
- `GET/POST /api/estoque`; `PUT/DELETE /api/estoque/{id}`. Payload: nome, categoria, unidade, quantidade e minimo (inteiros não negativos).
- `POST /api/estoque/{id}/movimentacoes`: `{"delta": 2}` para entrada ou valor negativo para saída. Rejeita saldo negativo e movimentação zero. Transação SQLite evita perda de atualização. Não há histórico/auditoria persistida de movimentações ainda.
- `POST /logout`: exige token CSRF. Links existentes usam `front/session.js` para encerrar a sessão.
- CRUD exige perfil owner; customer só acessa chat; admin acessa o painel administrativo. Provisionamento de usuários é local via manage.py, sem endpoint público de cadastro.

As páginas de conhecimento/estoque leem dados persistidos. Os botões estão conectados via front/crud.js: formulários de cadastro/edição, exclusão com confirmação, movimentação de estoque e ativação de artigos. Busca por texto e categorias funcionam localmente sobre a lista carregada. As operações usam sessão e token CSRF; erros aparecem na tela e os dados são recarregados após salvar. As demais telas e chats JavaScript existentes continuam demonstrativos. Os dados fixos antigos não foram importados. Métricas e o painel administrativo continuam demonstrativos. Pacientes, agendamentos e atendimentos agora usam registros persistidos por clínica; o dashboard ainda precisa ser alinhado a essas novas fontes.

### LLM e agente

`llm.py` implementa Groq Chat Completions com urllib (sem SDK adicional), timeout de 20s, resposta limitada e erros sanitizados. Referência oficial: https://console.groq.com/docs/api-reference . Configure GROQ_API_KEY e GROQ_MODEL apenas no servidor; não há chave no frontend. SMARTDENT_LLM_ENABLED=false por padrão: nenhuma chamada ao modelo. Habilitar true exige autorização e pode gerar custos. Nenhuma chamada real foi feita durante a implementação.

`POST /api/chat`, payload `{"pergunta":"..."}`, aceita owner/customer e exige CSRF. Retorna resposta, fontes candidatas e gerado_por_llm. `SMARTDENT_RETRIEVAL=pending` retorna 503 explicando a dependência semântica. `local_keyword` recupera artigos ativos do SQLite por palavras: recuperação lexical real, NÃO pgvector/semântica. Sem contexto, retorna falta de dados sem chamar LLM. Com contexto e LLM desativado, retorna 503. Não há resposta artificial de sucesso.

`rag.Retriever.retrieve(clinic, question, limit=4)` é um contrato Python interno: deve retornar documentos já filtrados pela clínica, com id, titulo, conteudo e status; empresa_id opcional deve corresponder à clínica. Guilherme deverá fornecer o contrato real do endpoint para um adaptador; nenhum endpoint externo foi inventado. O prompt restringe informações e trata documentos como dados, mas não garante que um modelo nunca alucine. As fontes são documentos enviados ao modelo, não prova automática de cada afirmação. O chat visual ainda depende de Caio.

### Testes

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Testes usam banco temporário, usuários fictícios e transporte LLM simulado. Cobrem hash/login/persistência em nova conexão, logout/CSRF/perfis, isolamento de clínicas, CRUD conhecimento, movimentação e quantidades inválidas, LLM desativado/timeout/resposta inválida/sucesso simulado, recuperação lexical e agente sem contexto. Esses arquivos não demonstram aprovação dos testes: consulte o relatório da execução. PostgreSQL, pgvector e chamada real Groq não foram verificados.

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

O esquema permanece provisório no adaptador records (tipos patients, appointments e attendance). Alinhar os novos campos paciente_id, data e mensagens com Guilherme antes da migração para PostgreSQL. Nenhuma tabela ou endpoint externo da equipe foi presumido.

Validação: 10 testes locais, incluindo CRUD dos três recursos, vínculo de paciente da mesma clínica, restrição de exclusão, mensagens preservadas, autorização e isolamento, validações de data/duração/status e renderização das telas. Sintaxe de records.js validada com Node. Cliques reais em navegador não foram verificados: não há navegador conectado disponível.
