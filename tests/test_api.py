import os
import re
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
from auth import hash_password

class APITests(unittest.TestCase):
    def environment(self):
        """Banco da suíte; test_postgres.PostgresAPITests troca por um PostgreSQL descartável."""
        return {'SMARTDENT_DB_PATH':self.tmp.name+'/db.sqlite3','SMARTDENT_DATABASE_URL':'','SMARTDENT_ENV':'development','SMARTDENT_RETRIEVAL':'local_keyword','SMARTDENT_LLM_ENABLED':'false','SMARTDENT_LLM_PROVIDER':'groq'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ,self.environment())
        self.env.start()
        self.client = TestClient(app)
        self.client.__enter__()
        for role,clinic,email in [('owner','a','a@example.test'),('owner','b','b@example.test'),('customer','a','c@example.test'),('admin','','admin@example.test')]:
            app.state.repository.add_user(dict(email=email,nome='Teste',iniciais='TT',role=role,empresa_id=clinic,password_hash=hash_password('senha-ficticia-testes')))

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.env.stop()
        self.tmp.cleanup()

    def login(self,email='a@example.test'):
        self.client.cookies.clear()
        page = self.client.get('/login').text
        token = re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
        response = self.client.post('/login',data={'email':email,'senha':'senha-ficticia-testes','csrf_token':token},follow_redirects=False)
        self.assertEqual(response.status_code,302)
        return {'X-CSRF-Token':self.client.get('/api/session').json()['csrf_token']}

    def test_auth_logout_permissions(self):
        for page in ['/', '/relatorios']:
            response=self.client.get(page,follow_redirects=False)
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.headers['location'],'/login')
        self.assertEqual(self.client.get('/api/estoque').status_code,401)
        page = self.client.get('/login').text
        token = re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
        response = self.client.post('/login',data={'email':'a@example.test','senha':'errada','csrf_token':token})
        self.assertIn('incorretos',response.text)
        self.assertEqual(self.client.get('/api/session').status_code,401)
        headers = self.login()
        self.assertEqual(self.client.post('/logout').status_code,403)
        self.assertEqual(self.client.post('/logout',headers=headers,follow_redirects=False).status_code,302)
        self.assertEqual(self.client.get('/api/session').status_code,401)
        self.login('c@example.test')
        self.assertEqual(self.client.get('/api/estoque').status_code,403)
        self.login('admin@example.test')
        self.assertEqual(self.client.get('/api/base-conhecimento').status_code,403)

    def test_knowledge_crud_isolation_and_validation(self):
        headers = self.login()
        data = dict(titulo='Teste',categoria='Teste',conteudo='Conteúdo fictício',status=True)
        response = self.client.post('/api/base-conhecimento',json=data,headers=headers)
        self.assertEqual(response.status_code,201)
        identifier = response.json()['id']
        data['conteudo']='Edição fictícia'
        self.assertEqual(self.client.put(f'/api/base-conhecimento/{identifier}',json=data,headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/base-conhecimento').json()[0]['conteudo'],data['conteudo'])
        self.assertEqual(self.client.post('/api/base-conhecimento',json=dict(data,titulo=' '),headers=headers).status_code,422)
        headers = self.login('b@example.test')
        self.assertEqual(self.client.get('/api/base-conhecimento').json(),[])
        self.assertEqual(self.client.put(f'/api/base-conhecimento/{identifier}',json=data,headers=headers).status_code,404)
        self.assertEqual(self.client.delete(f'/api/base-conhecimento/{identifier}',headers=headers).status_code,404)
        headers = self.login()
        self.assertEqual(self.client.delete(f'/api/base-conhecimento/{identifier}',headers=headers).status_code,204)

    def test_stock_and_chat_without_context(self):
        headers = self.login()
        data = dict(nome='Item fictício',categoria='Teste',unidade='un',quantidade=2,minimo=1)
        response = self.client.post('/api/estoque',json=data,headers=headers)
        self.assertEqual(response.status_code,201)
        identifier = response.json()['id']
        route = f'/api/estoque/{identifier}/movimentacoes'
        self.assertEqual(self.client.post(route,json={'delta':-3},headers=headers).status_code,400)
        self.assertEqual(self.client.post(route,json={'delta':1.5},headers=headers).status_code,422)
        self.assertEqual(self.client.post(route,json={'delta':True},headers=headers).status_code,422)
        self.assertEqual(self.client.post(route,json={'delta':3},headers=headers).json()['quantidade'],5)
        self.assertEqual(self.client.post('/api/estoque',json=dict(data,quantidade=-1),headers=headers).status_code,422)
        edited = dict(data, nome='Item editado', quantidade=5)
        self.assertEqual(self.client.put(f'/api/estoque/{identifier}',json=edited,headers=headers).status_code,200)
        headers_b = self.login('b@example.test')
        self.assertEqual(self.client.post(route,json={'delta':1},headers=headers_b).status_code,404)
        headers = self.login()
        self.assertEqual(self.client.delete(f'/api/estoque/{identifier}',headers=headers).status_code,204)
        self.assertEqual(self.client.get('/api/estoque').json(),[])
        response = self.client.post('/api/chat',json={'pergunta':'Pergunta fictícia'},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['gerado_por_llm'])

    def test_chat_context_disabled_and_simulated_model(self):
        headers = self.login()
        data = dict(titulo='Documento fictício',categoria='Teste',conteudo='Protocolo fictício alfa',status=True)
        self.assertEqual(self.client.post('/api/base-conhecimento',json=data,headers=headers).status_code,201)
        response = self.client.post('/api/chat',json={'pergunta':'Protocolo alfa'},headers=headers)
        self.assertEqual(response.status_code,503)
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value = 'Resposta simulada baseada no documento'
            response = self.client.post('/api/chat',json={'pergunta':'Protocolo alfa'},headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['gerado_por_llm'])
            self.assertEqual(response.json()['fontes'][0]['titulo'],data['titulo'])
            model.return_value.generate.assert_called_once()
        headers = self.login('b@example.test')
        with patch('app.create_llm') as model:
            response = self.client.post('/api/chat',json={'pergunta':'Protocolo alfa'},headers=headers)
            self.assertFalse(response.json()['gerado_por_llm'])
            model.return_value.generate.assert_not_called()

    def test_patients_appointments_attendance_crud_and_isolation(self):
        headers = self.login()
        patient = dict(nome='Paciente fictício',telefone='000',email='paciente@example.test',status='novo',plano='Teste',procedimentos=0)
        response = self.client.post('/api/pacientes',json=patient,headers=headers)
        self.assertEqual(response.status_code,201)
        patient_id = response.json()['id']
        appointment = dict(paciente_id=patient_id,data='2026-10-14',horario='10:30',duracao=30,procedimento='Procedimento fictício',dentista='Dentista teste',status='pendente')
        response = self.client.post('/api/agendamentos',json=appointment,headers=headers)
        self.assertEqual(response.status_code,201)
        appointment_id = response.json()['id']
        attendance = dict(cliente='Cliente fictício',preview='Solicitação fictícia',status='pending',canal='human')
        response = self.client.post('/api/atendimentos',json=attendance,headers=headers)
        self.assertEqual(response.status_code,201)
        attendance_id = response.json()['id']
        response = self.client.post(f'/api/atendimentos/{attendance_id}/mensagens',json={'texto':'Resposta humana fictícia'},headers=headers)
        self.assertEqual(response.status_code,201)
        self.assertEqual(len(response.json()['mensagens']),1)
        for page in ['/pacientes','/agendamentos','/atendimentos']:
            response = self.client.get(page)
            self.assertEqual(response.status_code,200)
            self.assertIn('/static/records.js',response.text)
            self.assertIn('data-action="create"',response.text)
            self.assertIn('data-action="edit"',response.text)
            self.assertIn('data-action="delete"',response.text)
        for route,data,identifier in [('pacientes',patient,patient_id),('agendamentos',appointment,appointment_id),('atendimentos',attendance,attendance_id)]:
            self.assertEqual(self.client.put(f'/api/{route}/{identifier}',json=data,headers=headers).status_code,200)
        self.assertEqual(len(next(a for a in self.client.get('/api/atendimentos').json() if a['id']==attendance_id)['mensagens']),1)
        self.assertEqual(self.client.delete(f'/api/pacientes/{patient_id}',headers=headers).status_code,409)
        self.assertEqual(self.client.post('/api/agendamentos',json=dict(appointment,data='data inválida'),headers=headers).status_code,422)
        self.assertEqual(self.client.post('/api/agendamentos',json=dict(appointment,duracao=0),headers=headers).status_code,422)
        self.assertEqual(self.client.post('/api/pacientes',json=dict(patient,nome=' '),headers=headers).status_code,422)
        self.assertEqual(self.client.post('/api/atendimentos',json=dict(attendance,status='inexistente'),headers=headers).status_code,422)
        headers_b = self.login('b@example.test')
        for route,data,identifier in [('pacientes',patient,patient_id),('agendamentos',appointment,appointment_id),('atendimentos',attendance,attendance_id)]:
            self.assertEqual(self.client.get(f'/api/{route}').json(),[])
            self.assertEqual(self.client.put(f'/api/{route}/{identifier}',json=data,headers=headers_b).status_code,404)
            self.assertEqual(self.client.delete(f'/api/{route}/{identifier}',headers=headers_b).status_code,404)
        self.assertEqual(self.client.post('/api/agendamentos',json=appointment,headers=headers_b).status_code,404)
        self.assertEqual(self.client.post(f'/api/atendimentos/{attendance_id}/mensagens',json={'texto':'Teste'},headers=headers_b).status_code,404)
        headers = self.login()
        for route,identifier in [('agendamentos',appointment_id),('pacientes',patient_id),('atendimentos',attendance_id)]:
            self.assertEqual(self.client.delete(f'/api/{route}/{identifier}',headers=headers).status_code,204)
        self.login('c@example.test')
        for route in ['pacientes','agendamentos','atendimentos']:
            self.assertEqual(self.client.get('/api/'+route).status_code,403)

    def test_suggestion_answers_latest_client_question_not_generic_subject(self):
        from seed_demo import seed
        headers=self.login()
        seed(app.state.repository,'a')
        attendance=app.state.repository.list('attendance','a')[0]
        identifier=attendance['id']
        question='Boa tarde! Quais são os horários de funcionamento e a política para remarcar uma consulta?'
        app.state.repository.append_message('a',identifier,dict(autor='client',texto=question,criado_em='2026-10-27T12:00:00+00:00'))
        app.state.repository.append_message('a',identifier,dict(autor='human',texto='Vou consultar essas informações.',criado_em='2026-10-27T12:01:00+00:00'))
        route=f'/api/atendimentos/{identifier}/sugestao'
        self.assertEqual(self.client.post(route).status_code,403)
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value='Funcionamos de segunda a sexta, das 08h às 18h, e aos sábados das 08h às 12h. Para remarcar, avise com 24 horas de antecedência. São dados fictícios de demonstração.'
            response=self.client.post(route,headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['gerado_por_llm'])
            titles={s['titulo'] for s in response.json()['fontes']}
            self.assertIn('Horários de funcionamento e agendamento',titles)
            self.assertIn('Políticas, convênios e pagamento',titles)
            messages=model.return_value.generate.call_args.args[0]
            self.assertIn(question,messages[-1]['content'])
            self.assertIn('24 horas',messages[-1]['content'])
            self.assertIn('Vou consultar essas informações.',messages[-1]['content'])
        self.assertEqual(len(next(a for a in app.state.repository.list('attendance','a') if a['id']==identifier)['mensagens']),2)
        headers_b=self.login('b@example.test')
        with patch('app.create_llm') as model:
            self.assertEqual(self.client.post(route,headers=headers_b).status_code,404)
            model.assert_not_called()
        headers_c=self.login('c@example.test')
        self.assertEqual(self.client.post(route,headers=headers_c).status_code,403)

    def test_owner_assistant_queries_followups_and_isolation(self):
        from seed_demo import seed
        from enhance_clinic import enhance
        from populate_conversations import populate
        headers=self.login()
        seed(app.state.repository,'a')
        enhance(app.state.repository,'a')
        populate(app.state.repository,'a')
        self.assertEqual(self.client.post('/api/assistente',json={'pergunta':'Agenda de amanhã'}).status_code,403)
        with patch('app.create_llm') as model:
            for question in ['Oi!','Quais são os agendamentos de amanhã?','Quais itens do estoque precisam de reposição?','Quantos pacientes estão cadastrados?','Quais reclamações foram identificadas?','Resumo da semana','Quais atendimentos estão pendentes?','Quais resumos estão pendentes?']:
                response=self.client.post('/api/assistente',headers=headers,json={'pergunta':question})
                self.assertEqual(response.status_code,200,question)
                self.assertEqual(response.json()['origem'],'registros')
                self.assertFalse(response.json()['gerado_por_llm'])
            model.assert_not_called()
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value='Na base fictícia, a limpeza custa R$ 180,00.'
            response=self.client.post('/api/assistente',headers=headers,json={'pergunta':'Qual o preço da limpeza?'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['origem'],'llm')
            self.assertTrue(response.json()['fontes'])
            model.return_value.generate.assert_called_once()
        response=self.client.post('/api/assistente',headers=headers,json={'pergunta':'E amanhã?','contexto':'agenda'})
        self.assertIn('amanhã',response.json()['resposta'])
        self.assertIn('/agendamentos',str(response.json()['acoes']))
        count=len(app.state.repository.list('patients','a'))
        self.client.post('/api/assistente',headers=headers,json={'pergunta':'Exclua os pacientes'})
        self.assertEqual(len(app.state.repository.list('patients','a')),count)
        self.assertEqual(self.client.post('/api/assistente',headers=headers,json={'pergunta':'Oi','contexto':'invalido'}).status_code,422)
        headers_b=self.login('b@example.test')
        response=self.client.post('/api/assistente',headers=headers_b,json={'pergunta':'Quantos pacientes estão cadastrados?'})
        self.assertNotIn('Ana',response.json()['resposta'])
        self.assertIn('0 paciente',response.json()['resposta'])
        headers=self.login('c@example.test')
        self.assertEqual(self.client.post('/api/assistente',headers=headers,json={'pergunta':'Quantos pacientes estão cadastrados?'}).status_code,403)

    def test_procedure_options_and_initial_guidance(self):
        self.assertEqual(self.client.get('/api/procedimentos').status_code,401)
        headers=self.login()
        self.assertIn('Avaliação ortodôntica',self.client.get('/api/procedimentos').json())
        self.assertEqual(len(self.client.get('/api/procedimentos').json()),10)
        response=self.client.post('/api/chat',json={'pergunta':'Tenho dor no dente superior'},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['tipo'],'orientacao_inicial')
        self.assertFalse(response.json()['gerado_por_llm'])

    def test_patient_conversation_creation_reuse_and_scope(self):
        headers=self.login()
        patient=dict(nome='Paciente integrado',email='integrado@example.test')
        response=self.client.post('/api/pacientes',json=patient,headers=headers)
        self.assertEqual(response.status_code,201)
        patient_id=response.json()['id']
        route=f'/api/pacientes/{patient_id}/atendimento'
        self.assertEqual(len(self.client.get('/api/atendimentos').json()),1)
        self.assertEqual(self.client.post(route).status_code,403)
        first=self.client.post(route,headers=headers).json()
        self.assertEqual(self.client.post(route,headers=headers).json()['id'],first['id'])
        self.client.post(f'/api/atendimentos/{first["id"]}/mensagens',headers=headers,json={'texto':'Mensagem preservada'})
        self.client.put(f'/api/pacientes/{patient_id}',headers=headers,json=dict(patient,nome='Nome atualizado'))
        conversation=self.client.post(route,headers=headers).json()
        self.assertEqual(conversation['cliente'],'Nome atualizado')
        self.assertEqual(conversation['mensagens'][0]['texto'],'Mensagem preservada')
        self.assertEqual(len(self.client.get('/api/atendimentos').json()),1)
        headers_b=self.login('b@example.test')
        self.assertEqual(self.client.post(route,headers=headers_b).status_code,404)
        self.assertEqual(self.client.get('/api/atendimentos').json(),[])

    def test_chat_page_uses_backend_client(self):
        self.login('c@example.test')
        response=self.client.get('/chat')
        self.assertEqual(response.status_code,200)
        self.assertIn('/static/ai-client.js',response.text)
        self.assertNotIn('const respostasIA',response.text)
        self.assertIn('window.smartdentAsk(texto)',response.text)
        self.assertEqual(self.client.get('/static/ai-client.js').status_code,200)

    def test_management_period_filters_use_persisted_records(self):
        from datetime import datetime, timedelta, timezone
        headers=self.login()
        data=dict(cliente='Teste de período',preview='Assunto fictício',status='pending',canal='human')
        identifier=self.client.post('/api/atendimentos',json=data,headers=headers).json()['id']
        stored=app.state.repository.list('attendance','a')[0]
        stored.pop('id')
        stored['criado_em']=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
        app.state.repository.save('attendance','a',stored,identifier)
        self.assertEqual(self.client.get('/api/gestao?dias=7').json()['metricas']['atendimentos_semana'],0)
        report=self.client.get('/api/gestao?dias=30').json()
        self.assertEqual(report['metricas']['atendimentos_semana'],1)
        self.assertEqual(len(report['grafico']['labels']),30)
        self.assertEqual(sum(report['grafico']['humano']),1)

    def test_sprint4_summary_reporting_and_isolation(self):
        headers=self.login()
        data=dict(cliente='Cliente de teste',preview='Cobrança divergente fictícia',status='pending',canal='human')
        identifier=self.client.post('/api/atendimentos',json=data,headers=headers).json()['id']
        route=f'/api/atendimentos/{identifier}/resumo'
        self.assertIsNone(self.client.get(route).json()['resumo'])
        self.assertEqual(self.client.post(route).status_code,403)
        self.assertEqual(self.client.post(route,headers=headers).status_code,503)
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value='Solicitação de revisão de cobrança. Sem desfecho registrado.'
            response=self.client.post(route,headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['desatualizado'])
            self.assertEqual(self.client.post(route,headers=headers).status_code,200)
            model.return_value.generate.assert_called_once()
        self.client.post(f'/api/atendimentos/{identifier}/mensagens',headers=headers,json={'texto':'Revisão fictícia em andamento'})
        self.assertTrue(self.client.get(route).json()['resumo']['desatualizado'])
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value=''
            self.assertEqual(self.client.post(route,headers=headers).status_code,503)
        # Falha de geração preserva o resumo antigo e sua indicação de desatualizado.
        self.assertTrue(self.client.get(route).json()['resumo']['desatualizado'])
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true'}),patch('app.create_llm') as model:
            model.return_value.generate.return_value='Revisão solicitada; confirmação pendente.'
            response=self.client.put(f'/api/atendimentos/{identifier}',headers=headers,json=dict(data,status='resolved'))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['resumo_status'],'gerado')
        self.client.put(f'/api/atendimentos/{identifier}/reclamacao',headers=headers,json=dict(reclamacao=True,categoria='preco_pagamento',motivo='Cobrança fictícia divergente'))
        report=self.client.get('/api/gestao?dias=7').json()
        self.assertEqual(report['metricas']['atendimentos_semana'],1)
        self.assertEqual(report['metricas']['resumos'],1)
        self.assertEqual(report['reclamacoes']['reclamacoes'],1)
        self.assertEqual(sum(report['grafico']['humano']),1)
        self.assertIsNone(report['metricas']['satisfacao'])
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true'}),patch('app.create_llm') as model:
            from llm import LLMUnavailable
            model.return_value.generate.side_effect=LLMUnavailable('Falha simulada')
            response=self.client.put(f'/api/atendimentos/{identifier}',headers=headers,json=dict(data,status='resolved',preview='Assunto modificado'))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['resumo_status'],'indisponivel')
            self.assertEqual(response.json()['status'],'resolved')
        for page in ['/', '/relatorios?dias=30']:
            response=self.client.get(page)
            self.assertEqual(response.status_code,200)
            self.assertIn('cobrança',response.text.lower())
            self.assertNotIn('91%',response.text)
        self.assertEqual(self.client.get('/api/gestao?dias=0').status_code,422)
        self.assertEqual(self.client.get('/relatorios?dias=91').status_code,422)
        self.login('b@example.test')
        self.assertEqual(self.client.get(route).status_code,404)
        self.assertEqual(self.client.get('/api/gestao').json()['metricas']['atendimentos_semana'],0)
        self.login('c@example.test')
        self.assertEqual(self.client.get('/api/gestao').status_code,403)
        self.assertEqual(self.client.get(route).status_code,403)
        headers=self.login()
        self.client.delete(f'/api/atendimentos/{identifier}',headers=headers)
        self.assertEqual(app.state.repository.list('summaries','a'),[])

    def test_crud_pages_render_safe_records_and_controls(self):
        headers = self.login()
        self.client.post('/api/base-conhecimento',json=dict(titulo='Artigo teste',categoria='Teste',conteudo='</script><script>alert(1)</script>',status=True),headers=headers)
        self.client.post('/api/estoque',json=dict(nome='Item teste',categoria='Teste',unidade='un',quantidade=2,minimo=1),headers=headers)
        for page in ['/base-conhecimento','/estoque']:
            response = self.client.get(page)
            self.assertEqual(response.status_code,200)
            self.assertIn('data-action="create"',response.text)
            self.assertIn('data-action="edit"',response.text)
            self.assertIn('data-action="delete"',response.text)
            self.assertIn('data-id="',response.text)
            self.assertIn('/static/crud.js',response.text)
            self.assertIn('id="crud-dialog"',response.text)
            self.assertNotIn('</script><script>alert(1)</script>',response.text)
        self.assertEqual(self.client.get('/static/crud.js').status_code,200)
        self.assertEqual(self.client.get('/static/crud.css').status_code,200)

    def test_knowledge_search_endpoint(self):
        headers = self.login()
        data = dict(titulo='Planos aceitos',categoria='Financeiro',conteudo='Aceitamos convênio Unimed fictício',status=True)
        self.assertEqual(self.client.post('/api/base-conhecimento',json=data,headers=headers).status_code,201)
        results = self.client.get('/api/base-conhecimento/busca',params={'q':'convênio Unimed'}).json()
        self.assertEqual([(r['titulo'],r['categoria']) for r in results],[(data['titulo'],data['categoria'])])
        self.assertIn('Unimed',results[0]['trecho'])
        self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':' '}).status_code,422)
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':'pending'}):
            self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':'convênio'}).status_code,503)
        self.login('b@example.test')
        self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':'convênio Unimed'}).json(),[])
        self.login('c@example.test')
        self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':'convênio'}).status_code,403)

    def test_complaints_classification_report_and_isolation(self):
        headers = self.login()
        ids = [self.client.post('/api/atendimentos',json=dict(cliente=f'Cliente {i}',preview=preview,status='pending',canal='human'),headers=headers).json()['id']
               for i,preview in enumerate(['Esperei uma hora para ser atendido','Cobraram valor diferente do combinado','Quero agendar uma limpeza'])]
        self.assertIn('tempo_espera',[c['categoria'] for c in self.client.get('/api/reclamacoes/categorias').json()])
        route = f'/api/atendimentos/{ids[0]}/reclamacao'
        self.assertEqual(self.client.put(route,json=dict(reclamacao=True,categoria='tempo_espera')).status_code,403)
        self.assertEqual(self.client.put(route,json=dict(reclamacao=True),headers=headers).status_code,422)
        self.assertEqual(self.client.put(route,json=dict(reclamacao=True,categoria='inexistente'),headers=headers).status_code,422)
        response = self.client.put(route,json=dict(reclamacao=True,categoria='tempo_espera',motivo='Atraso de uma hora'),headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual((response.json()['origem'],response.json()['rotulo'],response.json()['cliente']),('manual','Atrasos e tempo de espera','Cliente 0'))
        self.assertEqual(self.client.post(f'/api/atendimentos/{ids[1]}/reclamacao/classificar',headers=headers).status_code,503)
        with patch('app.create_llm') as model:
            model.return_value.generate.side_effect = ['{"reclamacao": true, "categoria": "preco_pagamento", "motivo": "Cobrança divergente"}',
                                                       '```json\n{"reclamacao": false, "categoria": null, "motivo": ""}\n```']
            body = self.client.post('/api/reclamacoes/classificar',headers=headers).json()
            self.assertEqual([c['attendance_id'] for c in body['classificados']],ids[1:])
            self.assertEqual([c['reclamacao'] for c in body['classificados']],[True,False])
            self.assertEqual(body['restantes'],0)
            self.assertNotIn('Cliente 1',str(model.return_value.generate.call_args_list))
            model.return_value.generate.side_effect = None
            model.return_value.generate.return_value = 'não é JSON'
            self.assertEqual(self.client.post(f'/api/atendimentos/{ids[2]}/reclamacao/classificar',headers=headers).status_code,503)
        report = self.client.get('/api/relatorios/reclamacoes',params={'dias':30}).json()
        self.assertEqual((report['atendimentos'],report['analisados'],report['pendentes'],report['reclamacoes']),(3,3,0,2))
        self.assertEqual((report['labels'],report['valores']),(['Atrasos e tempo de espera','Preços, cobrança e pagamento'],[1,1]))
        self.assertEqual(report['categorias'][0]['exemplos'],['Atraso de uma hora'])
        self.assertEqual(len(self.client.get('/api/reclamacoes').json()),3)
        headers_b = self.login('b@example.test')
        self.assertEqual(self.client.get('/api/reclamacoes').json(),[])
        self.assertEqual(self.client.get('/api/relatorios/reclamacoes').json()['reclamacoes'],0)
        self.assertEqual(self.client.put(route,json=dict(reclamacao=False),headers=headers_b).status_code,404)
        self.assertEqual(self.client.delete(route,headers=headers_b).status_code,404)
        self.assertEqual(self.client.post(f'/api/atendimentos/{ids[0]}/reclamacao/classificar',headers=headers_b).status_code,404)
        self.login('c@example.test')
        self.assertEqual(self.client.get('/api/relatorios/reclamacoes').status_code,403)
        headers = self.login()
        self.assertEqual(self.client.delete(route,headers=headers).status_code,204)
        self.assertEqual(self.client.delete(route,headers=headers).status_code,404)
        self.assertEqual(self.client.delete(f'/api/atendimentos/{ids[1]}',headers=headers).status_code,204)
        self.assertEqual(self.client.get('/api/relatorios/reclamacoes').json()['reclamacoes'],0)

if __name__ == '__main__': unittest.main()
