import os
import re
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
from auth import hash_password

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ,{'SMARTDENT_DB_PATH':self.tmp.name+'/db.sqlite3','SMARTDENT_ENV':'development','SMARTDENT_RETRIEVAL':'local_keyword','SMARTDENT_LLM_ENABLED':'false'})
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
        with patch('app.GroqClient') as model:
            model.return_value.generate.return_value = 'Resposta simulada baseada no documento'
            response = self.client.post('/api/chat',json={'pergunta':'Protocolo alfa'},headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['gerado_por_llm'])
            self.assertEqual(response.json()['fontes'][0]['titulo'],data['titulo'])
            model.return_value.generate.assert_called_once()
        headers = self.login('b@example.test')
        with patch('app.GroqClient') as model:
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
        self.assertEqual(len(self.client.get('/api/atendimentos').json()[0]['mensagens']),1)
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

if __name__ == '__main__': unittest.main()
