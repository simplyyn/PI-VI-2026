# Base de conhecimento para a apresentação

A curadoria de 06/11/2026 reúne 21 procedimentos, com descrição curta, termos de busca, referência de valor, escopo de cobrança e links das fontes. A preparação atualiza o banco local existente, preservando IDs e vínculos e criando um backup SQLite consistente antes da transação.

As faixas são referências pesquisadas. Não foi encontrada uma média nacional verificável para todos os procedimentos; não se calculou uma média misturando valores contratuais, particulares, técnicas ou unidades diferentes. Os números não se tornam preços oficiais da clínica por serem cadastrados.

## Fontes dos valores

- [DentMap — tabela de preços 2026](https://dentmap.com.br/blog/tabela-precos-procedimentos-dentista-2026): faixas publicadas para clínicas particulares do Sudeste, atualização declarada em abril de 2026. Foram usadas como referência editorial regional, sem auditar ou validar a amostra anunciada pelo editor. Exemplos: consulta R$ 150–400, limpeza R$ 150–500 e canal R$ 600–2.500.
- [CAASP — rede referenciada do interior, Agregado, 2025](https://www.caasp.org.br/arquivos/tabelasodonto/ODT_Tabela_Interior_Referenciado_Agregado_2025.pdf): valores contratuais específicos, identificados dessa forma nos artigos. Foram usados para procedimentos detalhados por faces, sessões ou modalidades. Não são média de consultórios particulares nem atualização de 2026.

Valores publicados com escopo pouco detalhado não foram rotulados automaticamente como preço por dente, arcada, implante completo ou tratamento completo. Coroas, exames, manutenções, materiais e cirurgias adicionais devem ter suas inclusões confirmadas no orçamento. A avaliação ortodôntica não recebeu um preço inventado: a fonte consultada não tinha uma faixa específica para essa consulta.

## Fontes das descrições

- [NHS — tratamentos odontológicos](https://www.nhs.uk/live-well/healthy-teeth-and-gums/dental-treatments/).
- [NHS — tratamento de canal](https://www.nhs.uk/tests-and-treatments/root-canal-treatment/).
- [NHS — clareamento](https://www.nhs.uk/tests-and-treatments/teeth-whitening/).
- [NHS — saúde das gengivas](https://www.nhs.uk/conditions/gum-disease/).
- [NHS — aparelhos](https://www.nhs.uk/tests-and-treatments/braces/).
- [NHS — saúde bucal infantil](https://www.nhs.uk/live-well/healthy-teeth-and-gums/taking-care-of-childrens-teeth/).
- [NHS — bruxismo](https://www.nhs.uk/symptoms/teeth-grinding/).
- [ADA/MouthHealthy — radiografias](https://www.mouthhealthy.org/all-topics-a-z/x-rays).

Os textos foram resumidos em português para informação geral. Não foram importadas regras de cobertura, preços britânicos, prescrições ou protocolos individuais. A indicação clínica permanece com o dentista.

## Preparação e reprodução

Para uma clínica já existente no SQLite local:

```powershell
.venv/Scripts/python.exe prepare_presentation.py --clinic clinica-teste
```

O comando lê apenas a configuração necessária do `.env`, não imprime segredos, recusa PostgreSQL e exige um banco existente dentro do projeto e owner na clínica. Gera `data/backups/presentation-*.sqlite3` antes de atualizar os registros. Não executa serviços externos ou migrações. Pode ser repetido sem duplicar artigos ou pacientes.

Ele atualiza os quatro artigos anteriores e acrescenta os 21 artigos individuais. Mantém os horários, formas de pagamento e antecedência de remarcação já adotados na apresentação; essas políticas são configurações do projeto, não informações inferidas dos sites pesquisados.

Os nomes de pacientes usados na apresentação foram normalizados para Ana Souza, Bruno Almeida, Carla Oliveira e Diego Santos. São os mesmos cadastros de apresentação, não pacientes reais importados: contatos, IDs, vínculos, status e históricos são preservados. Foram retirados os marcadores visíveis de exemplo das mensagens e dos nomes de profissionais. Não se alteraram senhas, logins ou o identificador da clínica. O nome de exibição da empresa pode passar a Clínica SmartDent quando o valor anterior era o identificador de teste.

O orçamento previamente preparado para avaliação e limpeza passa a uma faixa combinada de R$ 300–900, soma dos dois intervalos publicados, sem promessa de pacote fechado. O resumo antigo desse orçamento é revisado editorialmente e identificado no armazenamento como `revisao-editorial`; não se atribui essa revisão a uma chamada Gemini que não ocorreu. Demais resumos podem precisar de atualização se as mensagens mudaram.

Scripts antigos como `seed_demo.py` permanecem como fixtures e ferramentas históricas dos testes. Se usados para preparar uma instalação vazia, execute esta nova preparação por último. Os backups e a documentação conservam a procedência acadêmica; a limpeza dos rótulos da interface não transforma os cadastros em dados de uma clínica real.

Os 21 procedimentos também aparecem no formulário da agenda. A busca lexical foi ajustada para priorizar termos específicos e títulos, reduzindo a disputa de conteúdo genérico quando há muitos artigos semelhantes. Continua sendo busca lexical real, não pgvector.

## Conferência na aplicação

Atualize a página com Ctrl + F5 e consulte a Base de Conhecimento. Perguntas úteis para a apresentação:

- Quanto custa uma limpeza e o que está incluído?
- Qual a faixa de valor de um tratamento de canal?
- Qual a diferença entre limpeza e raspagem?
- Como funciona o clareamento?
- Quanto custa um implante? A coroa está incluída?
- Quais os horários e como remarcar uma consulta?

O comportamento da recuperação é testado com contexto real do catálogo e geração simulada. Não foi feita chamada real ao Gemini para certificar a redação dessas respostas.

Para outro computador, leve o banco atualizado de forma privada ou execute a preparação sobre uma base local existente. Os registros em `data/` não são enviados ao GitHub.

## Resultado da aplicação local

Em 06/11/2026, a preparação criou 21 artigos individuais, atualizou o guia de preços e o catálogo e ajustou os demais registros de apresentação em uma transação. A clínica ficou com 25 artigos ativos. A verificação SQLite retornou `ok`; os IDs de pacientes, conversas, agendamentos, vínculos e estoque permaneceram iguais, assim como as credenciais. A varredura dos campos visíveis não encontrou marcadores de exemplo, simulação ou demonstração. O backup consistente foi salvo em `data/backups/presentation-20261106-035420-155856.sqlite3`.

A suíte executada teve 88 testes Python: 59 aprovados e 29 ignorados por ausência de PostgreSQL descartável. As quatro verificações de comportamento JavaScript passaram. A recuperação no banco atualizado localizou os artigos específicos de canal e implante e os artigos de horários/remarcação. Não foi testada geração externa nem feita publicação no Git.
