# Entrega: conversa simples e agendamento assistido

## Executar

Na raiz do projeto, com o ambiente e as dependências já preparados:

```powershell
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

Abra http://127.0.0.1:8000. Após atualizar o código, use Ctrl + F5. Uma alteração no `.env` exige reiniciar o servidor.

O SQLite provisório fica em `data/smartdent.sqlite3`. Não foi substituído nem populado nesta entrega. Em outro computador, leve uma cópia consistente do banco e configure o `.env` privadamente; nenhum deles deve ir para o Git. Pare o servidor antes de copiar o banco. Credenciais já expostas devem ser substituídas.

## O que mudou

- Atendimentos mostra a conversa, autores, horários e um rascunho editável. As análises deixaram de ocupar o histórico.
- Resumo da IA abre um diálogo nativo, com fechar/Esc, carregamento, erros e botão para gerar/atualizar. Abrir um resumo salvo usa GET; gerar reutiliza o cache válido do backend.
- Reclamações e revisão manual ficam em Relatórios & IA. O backend, as classificações e os indicadores foram preservados.
- Rascunhos são separados por conversa enquanto a página permanece aberta. Sugestões e gravações atrasadas não podem atualizar outra conversa. Os rascunhos não sobrevivem a recarregar a página.
- Sugestão IA não envia a mensagem. Enviar registra uma mensagem do atendente no banco; não há integração de entrega por WhatsApp/e-mail.
- Agendamento pelo assistente usa uma ferramenta estruturada e validada no backend. A coleta é um fluxo determinístico em português, não uma LLM com acesso ao SQL. Isso permite agendar mesmo quando a API de geração está indisponível.
- Perguntas que combinam sintomas e informações práticas não descartam a parte documentada sobre horários/preços. Relatos urgentes continuam recebendo a orientação imediata existente, sem aguardar geração.

## Roteiro de apresentação

1. Mostre um paciente cadastrado e abra sua conversa. Confirme que o histórico ocupa a tela.
2. Clique em Resumo da IA. Um resumo existente não precisa de nova geração. Para um resumo ausente/desatualizado, a geração depende do Gemini.
3. Clique em Sugestão IA, leia e edite o rascunho. Mostre que ainda não entrou no histórico; clique em Enviar somente após revisar.
4. Abra o assistente e escreva `Agende uma consulta para o Pedro amanhã às 16h`. Use um paciente realmente cadastrado. Se não houver Pedro, use outro nome. Se houver homônimos, selecione pelo nome completo ou ID apresentado.
5. Responda aos campos faltantes: por exemplo `Consulta de avaliação`, o nome real do profissional usado na agenda e `30 minutos`. Não invente profissionais na apresentação; esses nomes são texto livre no cadastro atual.
6. Revise paciente, data, horário, procedimento, profissional e duração. Confira também o expediente da clínica. Digite `confirmar`. Só então a transação grava. Use `cancelar` para descartar apenas o rascunho.
7. A agenda aberta se atualiza sem fechar o widget. Em outra tela, use Conferir agenda. Repita a confirmação e mostre que não cria outra consulta.
8. Teste um horário ocupado. O bloqueio considera a duração, o profissional e o próprio paciente; consultas canceladas não ocupam o intervalo.
9. Em Relatórios & IA, selecione uma conversa para analisar/revisar reclamações e consulte o consumo registrado.

Datas relativas usam America/Sao_Paulo, com fallback UTC−3. Exemplos com “amanhã” mudam a cada dia. Não existe ainda uma grade estruturada de expediente/plantões/férias dos profissionais; ausência de conflito no banco não comprova disponibilidade real. Não se interpreta uma política em texto da base como autorização automática para agendar fora do expediente.

## Segurança e persistência

O agendamento requer owner autenticado e CSRF. O paciente é buscado apenas na clínica do usuário. Pacientes inativos não podem ser confirmados pelo agente. Campos obrigatórios seguem Appointment, incluindo precisão de minutos, data futura no agente e duração válida.

O rascunho fica na sessão assinada existente, limitado aos campos da operação; expira após 30 minutos, logout ou Limpar. Cancelar descarta o rascunho e não cancela consultas existentes. A coleta suporta os exemplos documentados e correções explícitas, como `amanhã às 17h`, `dentista Dra. Ana` e `procedimento Limpeza`; não é um interpretador irrestrito de linguagem natural. Mensagens do paciente e documentos recuperados nunca confirmam operações administrativas.

SQLite verifica conflitos e grava consulta + recibo de confirmação na mesma transação BEGIN IMMEDIATE. O recibo usa o armazenamento genérico já existente; não foi criada tabela ou executada migração. A proteção funciona mesmo com pedidos simultâneos e repetição da sessão anterior após reiniciar o processo. Um recibo de consulta removida não recria silenciosamente o registro.

A migração 004 habilita o agendamento conversacional e os recibos persistentes também no PostgreSQL. A revalidação de horários e a criação do recibo ocorrem na mesma transação. Para a demonstração já preparada com os dados locais, continue usando o SQLite ou provisione uma base PostgreSQL com registros próprios.

## IA e consumo

A configuração local conferida utiliza Gemini, modelo `gemini-3.5-flash-lite`, e busca lexical `local_keyword`. A busca usa artigos persistidos por clínica, mas não equivale a pgvector/busca semântica. Não foi trocado o provedor nem executada geração externa para testar esta entrega.

Clientes Gemini/Groq registram somente modelo, provedor, clínica, data, tentativas e contagens informadas pelo provedor em `data/llm-usage.jsonl`, ignorado pelo Git. Não registram chaves, perguntas ou respostas. O endpoint owner `GET /api/ia/uso` filtra a clínica e os relatórios mostram esse acumulado. A gravação de métricas falhar não invalida uma resposta obtida.

Esse registro começa agora: não reconstrói chamadas antigas, não inclui outras aplicações e não garante registrar consumo de chamadas malsucedidas, bloqueadas ou interrompidas. Contagens ausentes são marcadas como ausentes. Tokens de raciocínio e total informado são preservados quando disponíveis. Não se calcula saldo, custo exato ou cota do provedor com esses números. Para vários processos escrevendo intensamente, a telemetria em arquivo deve evoluir para armazenamento centralizado.

Requisições de geração possuem timeout de 20 segundos por tentativa. Somente HTTP 429/502/503/504 podem ter uma repetição, respeitando Retry-After de até 2 segundos. Esperas maiores retornam erro; não ocorre uma espera menor que a solicitada pelo provedor. Erros de autenticação, timeout e resposta inválida não são repetidos automaticamente. Uma geração pode consumir tokens em mais de uma tentativa. Essa política nunca repete gravações de agenda.

CRUD, agenda, consultas administrativas aos registros, classificações manuais e resumos já salvos continuam funcionando sem Gemini. Geração de resumos, sugestões contextuais e classificação por IA dependem da API. Não há respostas fingindo sucesso quando a geração falha.

Para cotas e despesas reais, selecione o mesmo projeto da chave no [Google AI Studio](https://aistudio.google.com/) e consulte Usage, Rate limits e Billing. O uso é sujeito a limites por período/modelo/projeto; outra chave no mesmo projeto não aumenta a cota. Não foi acessada sua conta para consultar o saldo. Consulte [limites](https://ai.google.dev/gemini-api/docs/rate-limits), [faturamento](https://ai.google.dev/gemini-api/docs/billing) e [metadados de geração](https://ai.google.dev/api/generate-content).

## Alternativa local, ainda não instalada

Este computador informou cerca de 31,9 GB de RAM, Radeon RX 7600 e aproximadamente 266 GB livres. Um modelo pequeno é uma opção a avaliar, sem garantia de latência ou qualidade equivalente ao Gemini. A compatibilidade/aceleração dessa GPU no runtime não foi validada. O computador da apresentação pode ter recursos diferentes.

Por exemplo, a distribuição [Gemma 3 4B no catálogo oficial do Ollama](https://ollama.com/library/gemma3/tags) informa um download de aproximadamente 3,4 GB para o modelo; o runtime e a execução precisam de espaço/memória adicionais. Isso ainda exigiria autorização para instalar/baixar, implementar um adaptador e medir respostas em português e latência na máquina da apresentação. Nada disso foi instalado ou apresentado como fallback pronto. Manter a integração atual e o agendamento independente da LLM reduz mudanças antes da apresentação.

## Verificações

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
node tests/attendance_ui.cjs
node --check front/attendance-analysis.js
node --check front/complaint-review.js
node --check front/records.js
node --check front/management.js
```

Os testes usam bancos temporários e modelos/HTTP simulados. PostgreSQL é ignorado sem SMARTDENT_TEST_DATABASE_URL descartável com pgvector; não use o banco real para a suíte. O teste Node verifica comportamento com DOM simulado, não aparência. A conferência visual de layout, responsividade e foco em navegador real continua necessária; testes de HTML e JavaScript não substituem isso.

Resultado executado em 06/11/2026: 83 testes Python, sendo 54 aprovados e 29 ignorados por ausência de PostgreSQL descartável. Quatro verificações de comportamento JavaScript aprovadas; verificações de sintaxe dos scripts alterados e `git diff --check` sem erros. A primeira tentativa de executar testes no sandbox encontrou bloqueio nas pastas temporárias; a execução concluída ocorreu fora dele, com bancos de teste isolados. Nenhuma geração externa foi executada.

Principais arquivos: `scheduling.py`, `usage.py`, `services.py`, `persistence.py`, `postgres.py`, `app.py`, `llm.py`, `rag.py`, `assistant.py`; templates de Atendimentos, Relatórios e base; scripts/estilos em `front/`; testes Python e `tests/attendance_ui.cjs`. Nenhum commit ou push foi feito nesta entrega.
