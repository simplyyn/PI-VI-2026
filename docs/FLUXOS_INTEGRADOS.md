# Cliente, atendimento e assistente administrativo

## Atualização preservada

A main local foi avançada por fast-forward de `1ffcdad` para `a4d51be`, recebendo a tela do colega. As melhorias locais foram guardadas em stash e reaplicadas sem conflitos. O stash foi mantido como segurança; não foi feito commit novo nem push. `.env`, SQLite e arquivos de acesso permanecem fora do Git.

A tela do colega usava respostas fixas no JavaScript. Seu layout foi reaproveitado, e o script foi substituído por acesso autenticado ao histórico persistente. `/demo` não é mais um chat anônimo com informações inventadas: paciente autenticado vê o portal; responsável vê as instruções de acesso em outra sessão.

## Executar e acessar

```powershell
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

1. No navegador normal, abra http://127.0.0.1:8000/login e entre com seu acesso de responsável da clínica (`owner`). Esse é o administrador operacional; o perfil global `admin` tem outra finalidade.
2. Abra `data/acesso-cliente.txt` localmente para consultar a credencial preparada para Pedro. Ela foi gerada aleatoriamente e não deve ser publicada ou enviada ao Git. Não reutiliza a senha do responsável.
3. Em uma janela anônima, abra http://127.0.0.1:8000/chat e entre com essa conta de paciente.
4. Na janela administrativa, abra Atendimentos e selecione Pedro. Os históricos são os mesmos. As duas telas consultam atualizações a cada quatro segundos quando estão visíveis.

O provisionamento aplicado em 10/11/2026 vinculou `pedro.cliente@smartdent.test` ao paciente ID 1 da `clinica-teste`, sem modificar sua senha administrativa. A senha do paciente está somente no arquivo privado. O backup anterior está em `data/backups/integrated-20261110-091302-941759.sqlite3`.

Para reproduzir em outra base SQLite existente, com autorização para preparar os dados:

```powershell
.venv/Scripts/python.exe prepare_integrated.py --clinic clinica-teste --patient-id 1 --email pedro.cliente@smartdent.test
```

O comando faz backup, exige owner e paciente ativo da clínica, mantém contas existentes e recusa vincular um usuário de outro perfil/clínica ou trocar um vínculo existente. Se a conta já existe, não troca sua senha nem revela o hash. Confira o ID do paciente antes de executar em outra base. Não executa migrações ou chamadas à IA.

## Aba Profissionais

O menu lateral possui **Profissionais**, em `/profissionais`. A página mostra os dois cadastros, áreas de atuação, procedimentos, situação e expediente. Há busca, edição com validação e um botão para abrir a agenda filtrada pelo identificador do profissional. Não foi criado um terceiro profissional ou um botão de cadastro adicional nessa tela.

Alterações de expediente, procedimentos e situação são verificadas contra consultas futuras. A edição é recusada quando deixaria uma consulta ativa fora do expediente, sem profissional ativo ou sem procedimento compatível. Alterar o nome atualiza o nome exibido nos agendamentos vinculados, sem perder os demais campos. Todas as alterações exigem perfil owner, CSRF e isolamento da clínica. Não há exclusão de profissionais por essa página.

A Dra. Marina era um nome livre dos primeiros agendamentos de apresentação, não um terceiro cadastro de profissional. A padronização de `repair_professionals.py` vincula os registros antigos aos cadastros Elias/Roberto, mantendo IDs, paciente, data, horário, duração, procedimento e status. O nome anterior fica em `appointment_reassignments` e na auditoria administrativa, além do backup. A associação de registros históricos não confirma uma atuação clínica real nem adiciona especialidades ou disponibilidade futura ao profissional. As validações atuais continuam obrigatórias para novos agendamentos.

O script antigo de geração de exemplos foi ajustado para usar Elias e Roberto; ele não cria mais agendamentos com Marina. A preparação deve ser executada explicitamente, somente no SQLite local da apresentação e após backup, nunca como migração automática.

Aplicação verificada em 10/11/2026: cinco consultas antigas foram reassociadas, mantendo as oito consultas existentes. A agenda passou a apresentar somente Elias e Roberto, com identificadores válidos. A comparação com o backup confirmou a preservação de pacientes, datas, horários, durações, procedimentos e status. Backup: `data/backups/professionals-20261110-100646-072462.sqlite3`. A integridade SQLite retornou `ok`. A suíte executada teve 117 testes: 88 aprovados e 29 de PostgreSQL ignorados. O teste de atualização da agenda também passou com preservação do novo filtro de profissional. Não houve validação visual em navegador nem chamada real à IA nessa alteração.

## Roteiro para apresentar

### 1. Pergunta do paciente

No portal, com resposta automática habilitada:

> Quanto custa uma limpeza dental?

A mensagem é gravada antes da geração. A IA usa a base daquela clínica e os preços próprios, se cadastrados. Se falhar por conexão/cota, a mensagem continua disponível para a equipe; não se grava uma resposta fictícia de sucesso. Cada tentativa de envio tem uma chave para evitar duplicação em repetição de requisição.

### 2. Pendência e resposta humana

Desmarque “Receber resposta automática da IA” ou peça “quero falar com atendente” e envie uma pergunta. No chatbot administrativo:

> Quantos clientes estão sem resposta?
> Quantas mensagens estão sem responder?
> Mostre quem está esperando há mais tempo.

O relatório informa conversas, pacientes vinculados únicos, mensagens e início da espera. Conversas sem vínculo cadastral são discriminadas, sem inventar uma quantidade de pacientes únicos. É possível abrir os atendimentos pelos links.

Responda pelo campo do atendimento e confira a chegada no portal. A mensagem é entregue pelo site, não por WhatsApp ou e-mail. Ler a conversa, gerar sugestão, mudar seu status ou marcar revisão manual não envia mensagem.

Após pedir atendimento humano, o portal mantém o encaminhamento. Para voltar à IA, marque novamente a opção de resposta automática: isso retoma explicitamente o assistente da própria conversa. Não altera conversas de outras pessoas.

### 3. Respostas em lote

No chatbot do responsável:

> Prepare respostas para todos os clientes sem resposta.

Abra “Revisar respostas”. O lote contém no máximo cinco conversas, processadas sequencialmente para limitar consumo. Edite cada resposta, selecione quais enviar e confirme uma vez no botão da página.

- Uma prévia não é envio.
- Se chegaram mensagens novas ou outra resposta alterou a conversa, o item precisa de revisão.
- Falhas são apresentadas por item; sucesso em uma conversa não é desfeito porque outra mudou.
- Repetir o envio não duplica mensagens; o resultado distingue enviadas agora de já enviadas.
- Digitar “confirmar” no chat não envia um lote sem revisão: o assistente direciona à página de seleção.
- Uma prévia recente idêntica pode ser reutilizada por cinco minutos. O lote expira após trinta minutos.

### 4. Elias e Roberto

Em Agendamentos, expanda “Profissionais e expediente”. Foram preparados:

- **Elias:** foco em avaliação cirúrgica, cirurgia oral e reabilitação; duração padrão de 60 minutos.
- **Roberto:** foco em prevenção e clínica geral; duração padrão de 30 minutos.

Expediente de ambos: segunda a sexta, 08h–12h e 13h–18h; sábado, 08h–12h; sem expediente aos domingos. São dados da apresentação, não credenciais ou uma escala de uma clínica real. Não se descreve um profissional como inferior ao outro.

Cada profissional possui ID, procedimentos atendidos, expediente e situação ativa. Foram preparados dois agendamentos futuros para Pedro, um em cada agenda, respeitando os intervalos e o conflito do paciente. Os registros históricos anteriores foram preservados.

No chatbot administrativo:

> Quais profissionais e especialidades estão cadastrados?
> Quais horários estão disponíveis para o Elias amanhã?
> Agende uma consulta para o Pedro amanhã às 16h.

Informe o procedimento quando perguntado. Limpeza direciona ao cadastro compatível de Roberto; uma solicitação genérica de cirurgia complexa direciona para **avaliação cirúrgica**, não para confirmação de cirurgia. Revise e confirme.

No portal do paciente:

> Quero marcar uma limpeza.
> Quero marcar uma cirurgia super complicada no meu dente.

O portal usa somente o paciente autenticado e os profissionais da sua clínica. Oferece horários cadastrados, pede data/horário e exibe a prévia antes de gravar. Para cirurgia, oferece avaliação com Elias. Conflitos, duração, expediente, profissional e agenda do paciente são verificados novamente dentro da transação. Horários livres não são reservados enquanto o usuário está revisando.

Datas relativas usam America/Sao_Paulo; estão previstos hoje, amanhã, depois de amanhã e datas explícitas. Dias da semana por extenso e interpretações muito livres podem exigir uma data objetiva. A linguagem de agendamento é um fluxo validado por regras; não depende da disponibilidade da API de geração.

### 5. Operações administrativas

Exemplos para o chatbot do responsável:

> Atualize o telefone do Pedro para 11999990000.
> Altere a prioridade do atendimento do Pedro para urgente.
> Marque o atendimento do Pedro como revisado.
> Cadastre um item no estoque: gaze, categoria material, unidade pacote, quantidade 10, mínimo 2.
> Registre a saída de duas unidades de gaze.
> Atualize o artigo [título ou ID] com o novo conteúdo: [texto].
> Remarque a consulta ID [número] para [data e horário].
> Envie para o Pedro a mensagem: “Olá, Pedro. A equipe pode confirmar seu horário.”

A IA interpreta o pedido e propõe JSON para uma ferramenta permitida. O backend resolve o registro dentro da clínica, valida campos e apresenta a prévia. Apenas a confirmação executa a transação e registra auditoria. Os dados anteriores são revalidados; se mudaram, é necessário revisar um novo pedido. A IA não recebe conexão SQL, acesso a arquivos, senhas ou liberdade para chamar qualquer endpoint.

Operações disponíveis: cadastro/alteração de pacientes, estoque e conhecimento; movimentação de estoque; preço próprio de procedimento; status/prioridade/revisão de atendimento; mensagem individual; remarcação/cancelamento de consulta; exclusão de registro com confirmação específica. Use IDs quando houver nomes repetidos. Exclusões exigem `EXCLUIR [ID]`, e dependências do serviço continuam sendo verificadas.

Não é um assistente irrestrito que pode fazer qualquer coisa no computador. Profissionais, privilégios de usuário, arquivos, credenciais e migrações não são ferramentas expostas ao modelo. Pedidos incompletos ou não reconhecidos podem exigir reformulação. Revisão humana da prévia continua necessária; a interpretação da linguagem depende da LLM, e não foi testada com chamadas reais nesta entrega.

Prioridade é administrativa e aparece na conversa. Não é um diagnóstico ou uma triagem clínica. “Respondido” pedido manualmente é tratado como revisão, sem inventar uma mensagem enviada. A contagem de espera continua baseada em mensagens reais.

### 6. Preço próprio e referências

O catálogo mantém referências pesquisadas. Não foi presumido que a clínica cobrava R$ 50 por limpeza.

Para cadastrar um preço efetivo:

> Defina o preço da limpeza dental em R$ 60 por sessão.

Confira o procedimento, a unidade e o valor antes de confirmar. Veja o resultado na seção “Preços próprios da clínica” da Base de Conhecimento ou pergunte “Quais os preços da clínica cadastrados?”.

Depois, uma alteração com valor anterior só é aceita se ele corresponder ao preço próprio vigente. Referências de mercado não são substituídas globalmente. O contexto da resposta ao paciente prioriza o preço próprio cadastrado; as faixas de pesquisa continuam identificadas como referências.

### 7. Relatórios

> Consultas por profissional.
> Agenda do Elias amanhã.
> Quais as consultas canceladas nos últimos 30 dias?
> Quais procedimentos foram mais agendados nos últimos 30 dias?
> Quais atendimentos têm prioridade urgente?
> Quais itens estão com estoque baixo?

Relatórios de agenda informam o período usado: próximos sete dias por padrão, hoje/amanhã quando especificado ou últimos N dias, de 1 a 365. Não são apresentadas satisfação, receita ou duração real do atendimento sem dados que comprovem essas métricas.

## Regras de mensagens sem resposta

A página `/respostas` lista as pendências ao abrir, sem precisar gerar sugestões e sem consumir a API de IA. Os cartões exibem nome, quantidade, início da espera, última mensagem e link para o atendimento. Gerar a prévia é uma ação separada, e o botão de envio só fica disponível com um lote pronto para revisão. A regra global `[hidden]` mantém controles ocultos mesmo quando as classes de botão usam `display:flex`. `node tests/batch_replies_ui.cjs` cobre a abertura sem lote, um lote pronto, o processamento em andamento e falha de carregamento.

O histórico usa ordem de gravação e horário. Uma mensagem de paciente posterior à última resposta válida entra na espera. Sugestões não enviadas não entram no histórico; avisos de encaminhamento e falta de contexto não encerram a espera. Em conversas escaladas, exige-se uma resposta humana. Uma resposta automática válida em conversa não escalada encerra a espera da equipe para aquele trecho. Novas mensagens depois de resolver uma conversa reabrem o status como pendente.

Mensagens, recibos, lotes, vínculos e auditoria são gravados em registros da clínica. Recibos protegem repetições mesmo após reiniciar o processo. Falhas ou queda durante geração mantêm a mensagem do paciente, sem gerar novamente silenciosamente; a equipe pode assumir o atendimento.

## Arquivos principais

- `workflows.py`: vínculo do paciente, pendências, entrega idempotente, lotes e auditoria.
- `professionals.py`: profissionais, expediente, disponibilidade e agendamento do paciente.
- `admin_actions.py`: ferramentas, proposta, validação, confirmação e auditoria de alterações.
- `assistant_admin.py`: comandos administrativos, relatórios e revisão de lote.
- `integrated_api.py`: rotas autenticadas do portal, lotes, preços e profissionais.
- `persistence.py`: unidade de trabalho SQLite com transação compartilhada entre serviços.
- `prepare_integrated.py`: preparação explícita e idempotente, com backup e credencial privada.
- `app.py`, `services.py`, `scheduling.py`, `rag.py`, `assistant.py`: integração e reaproveitamento das regras existentes.
- Templates `demo_chat.html`, `client_access.html`, `batch_replies.html`, `atendimentos.html`, `agendamentos.html`, `conhecimento.html` e `base.html`.
- Scripts `customer-chat.js`, `batch-replies.js`, `clinic-overview.js`, `records.js` e estilos de atendimento.
- Testes `test_workflows.py`, `test_integrated_api.py` e ajustes dos testes anteriores.

## Validação e limites

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -q
node tests/attendance_ui.cjs
node --check front/customer-chat.js
node --check front/batch-replies.js
node --check front/records.js
```

Os testes usam bancos isolados, sessões de diferentes perfis e modelos simulados. Cobrem comunicação, privacidade, pendências, lotes com falha parcial, versões, repetição, concorrência, ferramentas autorizadas, preços, prioridade, disponibilidade e conflitos.

Resultado executado em 10/11/2026: 108 testes Python, sendo 79 aprovados e 29 ignorados por ausência de PostgreSQL descartável. Após o ajuste final dos links de resultado, os 12 testes de workflows passaram novamente. As quatro verificações JavaScript do atendimento, a análise de sintaxe dos scripts alterados e dos três scripts embutidos em base.html e `git diff --check` passaram. A leitura de integridade do SQLite real retornou `ok`; foram confirmados dois profissionais, um vínculo de acesso do paciente e dois agendamentos dos novos profissionais. As credenciais permaneceram em arquivo ignorado pelo Git.

Não foram feitas chamadas reais ao Gemini. A conferência visual via computer-use foi interrompida porque a ferramenta não conseguiu determinar a URL do navegador com confiança; nenhuma tela foi declarada visualmente aprovada. A prévia preparada para essa tentativa usava um banco de teste separado e servidor somente de leitura, encerrado após a interrupção. Confira o layout e o fluxo manualmente nos dois navegadores antes da apresentação.

Os novos fluxos administrativos, vínculos, lotes e agendas estruturadas usam o armazenamento genérico **SQLite de desenvolvimento** já existente. Não foi criada tabela nem executada migração. O adaptador PostgreSQL ainda precisa receber contrato de unidade de trabalho e armazenamento para esses novos tipos, com alinhamento e testes junto de Guilherme. Não aponte a apresentação para PostgreSQL esperando que esses novos fluxos estejam adaptados: o backend os recusa explicitamente quando o contrato não está disponível.

Limites atuais: atualização por consulta periódica, não WebSocket; até cinco sugestões por lote; uma operação administrativa por confirmação; interpretação de linguagem sujeita ao modelo e aos comandos disponíveis; disponibilidade futura pode mudar entre a oferta e a confirmação. Gemini pode impor cotas e timeout. Não há integração WhatsApp/e-mail nem garantia de resposta automática se o provedor estiver indisponível.

Para outra máquina, leve o banco atualizado e a configuração privadamente. O Git transporta o código, não o SQLite, o `.env` ou as senhas locais.

## Estoque e respostas do assistente

Consultas sobre itens em falta mostram saldo zero e saldo no mínimo ou abaixo dele, em grupos separados. O assistente calcula a diferença até o mínimo usando os registros da clínica, sem consumir tokens e sem registrar compras ou entradas. Itens exatamente no mínimo recebem alerta de reposição, conforme a regra RF009 de Guilherme. A classificação usa services.stock_view, a mesma função da tela e da API. Nesse limite, a diferença até o mínimo é zero, e o chatbot orienta programar a compra. A consulta geral continua disponível e apresenta o panorama do estoque.

`inventory.py` concentra essa apresentação; `tests/test_inventory.py` verifica filtros, cálculos, isolamento e expansão sem duplicação. `expand_inventory.py --clinic clinica-teste` adiciona materiais ausentes, preserva saldos existentes e cria um backup antes da alteração. Execute com o Python da `.venv`. Os saldos adicionados são dados preparados para a apresentação acadêmica, não resultado de inventário físico da clínica.

Na preparação de 10/11/2026 foram adicionados 20 materiais, totalizando 25: três esgotados, seis abaixo do mínimo e 16 com saldo no mínimo ou acima (contagem anterior à integração RF009). Os cinco registros anteriores foram preservados e a integridade SQLite foi conferida. Backup: `data/backups/inventory-20261110-103424-302001.sqlite3`. Esses números mudam conforme as operações realizadas nas telas.

## Correção: escolha de horário e agenda em outra janela

O relato `pode ser dia 12 /11/2026 as 8:30` revelou que o espaço antes da barra fazia o leitor antigo capturar um fragmento da data. `booking_input.py` normaliza os separadores e valida formatos de data/horário sem aproveitar fragmentos inválidos. Colar uma linha com vários horários agora pede que se escolha somente um, em vez de selecionar o primeiro silenciosamente.

O portal mantém a revisão antes de gravar e mostra **Confirmar agendamento** quando a prévia está pronta. Informar data/horário ainda não é confirmação; a consulta aparece na agenda após o sucesso da gravação. A ação é retornada no histórico para a interface distinguir prévia, erro e conclusão.

A agenda administrativa agora consulta atualizações a cada quatro segundos e ao recuperar o foco. Isso cobre confirmações feitas em outra janela, inclusive anônima. A atualização preserva busca, status e data selecionada: uma consulta marcada para 12/11 não é exibida enquanto a agenda estiver filtrada em 17/11. Modais de edição abertos suspendem essa atualização para preservar os dados em preenchimento.

Verificações: `tests/test_booking_input.py` cobre o texto relatado, datas malformadas e listas de horários; `tests/test_integrated_api.py` verifica que a prévia não grava e que a confirmação do paciente aparece na agenda do responsável sem duplicação; `node tests/agenda_refresh.cjs` verifica atualização externa com preservação dos três filtros. Os testes usam dados isolados, sem chamadas reais à IA e sem modificar o pedido real do paciente.
