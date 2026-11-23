import json
import os
import re
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
from auth import hash_password
from services import Appointment, Patient, ClinicRecords
from prepare_integrated import prepare


class IntegratedAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.password='api-isolated-password';cls.hashed=hash_password(cls.password)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'SMARTDENT_DATABASE_URL':'','SMARTDENT_DB_PATH':self.tmp.name+'/db.sqlite3','SMARTDENT_ENV':'development','SMARTDENT_LLM_ENABLED':'false','SMARTDENT_RETRIEVAL':'local_keyword','SMARTDENT_LLM_PROVIDER':'groq','SMARTDENT_USAGE_PATH':self.tmp.name+'/usage.jsonl'})
        env.start();self.addCleanup(env.stop)
        self.client=TestClient(app);self.client.__enter__();self.addCleanup(lambda:self.client.__exit__(None,None,None))
        self.repo=app.state.repository
        for email,clinic in [('owner@a.test','a'),('owner@b.test','b')]:self.repo.add_user(dict(email=email,role='owner',empresa_id=clinic,nome='Responsável',password_hash=self.hashed))
        self.patient=ClinicRecords(self.repo,'a').save('patients',Patient(nome='Pedro',status='ativo'))
        self.account=prepare(self.repo,'a',self.patient['id'],'patient@a.test')
        other=ClinicRecords(self.repo,'a').save('patients',Patient(nome='Outra Pessoa',status='ativo'))
        self.other=prepare(self.repo,'a',other['id'],'other@a.test')

    def login(self,email,password=None):
        self.client.cookies.clear();page=self.client.get('/login').text
        token=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
        response=self.client.post('/login',data={'email':email,'senha':password or self.password,'csrf_token':token},follow_redirects=False)
        self.assertEqual(response.status_code,302)
        return {'X-CSRF-Token':self.client.get('/api/session').json()['csrf_token']}

    def test_customer_owner_roundtrip_and_customer_isolation(self):
        h=self.login('patient@a.test',self.account['password'])
        response=self.client.post('/api/cliente/mensagens',headers=h,json={'texto':'Quero falar com atendente','request_id':'request-0001'})
        self.assertEqual(response.status_code,200);aid=response.json()['atendimento_id']
        self.assertEqual(self.client.get('/api/pendencias').status_code,403)
        self.assertEqual(self.client.post('/api/cliente/mensagens',headers=h,json={'texto':'x','request_id':'request-0002','patient_id':999}).status_code,422)
        h=self.login('owner@a.test')
        p=self.client.get('/api/pendencias').json();self.assertEqual((p['conversas'],p['mensagens']),(1,1))
        for _ in range(2):self.assertEqual(self.client.post(f'/api/atendimentos/{aid}/mensagens',headers=h,json={'texto':'Olá, Pedro. Como posso ajudar?','request_id':'owner-reply-0001'}).status_code,201)
        self.assertEqual(self.client.get('/api/pendencias').json()['mensagens'],0)
        self.login('patient@a.test',self.account['password']);messages=self.client.get('/api/cliente/conversa').json()['mensagens']
        self.assertEqual(sum(m['autor']=='human' for m in messages),1)
        self.login('other@a.test',self.other['password'])
        self.assertNotIn('Olá, Pedro',str(self.client.get('/api/cliente/conversa').json()))
        self.login('owner@b.test');self.assertEqual(self.client.get('/api/pendencias').json()['conversas'],0)

    def test_patient_scope_blocks_private_and_unrelated_questions_before_generation(self):
        headers = self.login('patient@a.test', self.account['password'])

        def send(question, key):
            response = self.client.post('/api/cliente/mensagens', headers=headers,
                                        json={'texto': question, 'request_id': key})
            self.assertEqual(response.status_code, 200)
            return response.json()

        with patch('app.create_llm') as model:
            reply = send('Quanto é dois mais dois?', 'scope-unrelated')
            self.assertIn('assuntos da clínica', reply['mensagens'][-1]['texto'])
            reply = send('Quero marcar uma limpeza', 'scope-booking')
            self.assertEqual(reply['acao']['estado'], 'escolher_horario')
            self.assertTrue(reply['acao']['opcoes'][0]['horarios'])
            for key, question in (
                ('scope-revenue', 'Quanto vocês faturaram este mês?'),
                ('scope-count', 'Quantas limpezas vocês fizeram esse mês?'),
                ('scope-mixed', 'Quanto custa a limpeza e qual foi o faturamento?'),
            ):
                reply = send(question, key)
                self.assertIn('restritos à equipe', reply['mensagens'][-1]['texto'])
                self.assertFalse(reply['mensagens'][-1]['gerado_por_llm'])
                self.assertEqual(reply['acao']['estado'], 'escolher_horario')
            model.assert_not_called()

        self.repo.save('kb', 'a', dict(titulo='Limpeza dental', categoria='Procedimentos',
                                       conteudo='O preço público é R$ 80.', status=True))
        self.repo.save('kb', 'a', dict(titulo='Limpeza: relatório interno', categoria='Interno',
                                       conteudo='O faturamento confidencial é R$ 999.', status=True))
        with patch('app.create_llm') as model:
            model.return_value.generate.return_value = 'A limpeza custa R$ 80.'
            reply = send('Quanto custa a limpeza?', 'scope-public')
            self.assertTrue(reply['mensagens'][-1]['gerado_por_llm'])
            prompt = repr(model.return_value.generate.call_args)
            self.assertIn('R$ 80', prompt)
            self.assertNotIn('R$ 999', prompt)
            self.assertNotIn('dois mais dois', prompt)

    def test_only_marked_cleanings_count_for_the_owner_and_period(self):
        from management import LOCAL_ZONE

        def create(day, status='confirmado'):
            return ClinicRecords(self.repo, 'a').save('appointments', Appointment(
                paciente_id=self.patient['id'], data=day, horario='17:00', duracao=30,
                procedimento='Limpeza dental (profilaxia)', dentista='Roberto', status=status,
            ))

        current = create('2026-11-03')
        create('2026-11-04')  # Confirmado, sem realização registrada.
        cancelled = create('2026-11-05', 'cancelado')
        future = create('2026-11-24')
        previous = create('2026-10-27')
        now = datetime(2026, 11, 20, 12, tzinfo=LOCAL_ZONE)

        def complete(appointment, headers, value=True):
            return self.client.put(f"/api/agendamentos/{appointment['id']}/realizacao", headers=headers,
                                   json={'realizado': value})

        patient_headers = self.login('patient@a.test', self.account['password'])
        self.assertEqual(complete(current, patient_headers).status_code, 403)
        self.assertEqual(self.client.post('/api/assistente', headers=patient_headers,
                                         json={'pergunta': 'Quantas limpezas fizemos?'}).status_code, 403)
        self.assertEqual(complete(current, self.login('owner@b.test')).status_code, 404)
        headers = self.login('owner@a.test')
        with patch('app.datetime') as calendar, patch('assistant.datetime') as reporting, patch('app.create_llm') as model:
            calendar.now.return_value = reporting.now.return_value = now
            self.assertEqual(complete(current, {}).status_code, 403)
            self.assertEqual(complete(current, headers).json()['realizado_em'], '2026-11-03')
            self.assertEqual(complete(current, headers).json()['realizado_em'], '2026-11-03')
            self.assertEqual(complete(previous, headers).status_code, 200)
            self.assertEqual(complete(cancelled, headers).status_code, 409)
            self.assertEqual(complete(future, headers).status_code, 409)

            def ask(question):
                answer = self.client.post('/api/assistente', headers=headers, json={'pergunta': question})
                self.assertEqual(answer.status_code, 200)
                return answer.json()['resposta']

            self.assertIn('1 limpeza(s)', ask('Quantas limpezas nós fizemos ao todo esse mês?'))
            self.assertIn('1 limpeza(s)', ask('Quantas limpezas fizemos no mês passado?'))
            self.assertIn('2 limpeza(s)', ask('Quantas limpezas fizemos ao todo?'))
            self.assertEqual(complete(current, headers, False).status_code, 200)
            self.assertIn('0 limpeza(s)', ask('Quantas limpezas fizemos este mês?'))
            model.assert_not_called()

    def test_patient_area_is_authenticated_and_uses_integrated_script(self):
        self.assertEqual(self.client.get('/demo',follow_redirects=False).status_code,302)
        self.login('owner@a.test');self.assertIn('janela anônima',self.client.get('/demo').text)
        self.login('patient@a.test',self.account['password']);page=self.client.get('/chat').text
        self.assertIn('/static/customer-chat.js',page);self.assertNotIn('getRespostaIA',page)
        self.assertNotIn('const respostas =',page)
        self.assertEqual(self.client.get('/api/estoque').status_code,403)

    def test_automatic_answer_is_persisted_and_batch_requires_confirmation(self):
        h=self.login('patient@a.test',self.account['password'])
        with patch('app.create_llm') as llm:
            self.repo.save('kb','a',dict(titulo='Limpeza',categoria='Procedimentos',conteudo='Limpeza: R$ 80.',status=True))
            llm.return_value.generate.return_value='A limpeza tem valor cadastrado de R$ 80.'
            r=self.client.post('/api/cliente/mensagens',headers=h,json={'texto':'Quanto custa a limpeza?','request_id':'automatic-0001'})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()['mensagens'][-1]['autor'],'ai')
        self.client.post('/api/cliente/mensagens',headers=h,json={'texto':'Outra dúvida','request_id':'human-0001','resposta_automatica':False})
        h=self.login('owner@a.test')
        with patch('app.create_llm') as llm:
            llm.return_value.generate.return_value='Vou conferir sua dúvida.'
            batch=self.client.post('/api/respostas/lotes',headers=h).json()
        item=batch['items'][0];route=f"/api/respostas/lotes/{batch['id']}/enviar"
        page=self.client.get('/respostas?lote='+str(batch['id'])).text
        self.assertIn('id="pending-conversations"',page)
        self.assertIn('id="batch-preview" hidden',page)
        self.assertIn('id="send-replies" class="btn-primary" hidden disabled',page)
        payload={'items':[{'id':item['id'],'texto':'Resposta revisada'}]}
        self.assertEqual(self.client.post(route,headers=h,json=payload).status_code,422)
        payload['confirmado']=True
        first=self.client.post(route,headers=h,json=payload).json()
        self.assertEqual(first['enviados'],1)
        replay=self.client.post(route,headers=h,json=payload).json()
        self.assertEqual(replay['enviados'],0)
        self.assertEqual(replay['resultados'][0]['status'],'ja_enviado')
        self.login('owner@b.test');self.assertEqual(self.client.get(f"/api/respostas/lotes/{batch['id']}").status_code,404)

    def test_admin_model_plans_are_reviewed_and_not_sql_execution(self):
        h=self.login('owner@a.test')
        question={'pergunta':'Atualize o telefone do Pedro para 11999990000'}
        with patch('app.create_llm') as llm:
            llm.return_value.generate.return_value=json.dumps(dict(ferramenta='paciente_atualizar',alvo=self.patient['id'],dados={'telefone':'11999990000'}))
            r=self.client.post('/api/assistente',headers=h,json=question)
        self.assertEqual(r.status_code,200)
        self.assertEqual(ClinicRecords(self.repo,'a').get('patients',self.patient['id'])['telefone'],'')
        r=self.client.post('/api/assistente',headers=h,json={'pergunta':'confirmar'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(ClinicRecords(self.repo,'a').get('patients',self.patient['id'])['telefone'],'11999990000')
        with patch('app.create_llm') as llm:
            llm.return_value.generate.return_value='{"ferramenta":"executar_sql","dados":{"sql":"DROP TABLE users"}}'
            result=self.client.post('/api/assistente',headers=h,json={'pergunta':'Altere o banco'})
            self.assertEqual(result.status_code,200);self.assertIn('permitida',result.json()['resposta'])
        self.assertIsNotNone(self.repo.user('owner@a.test'))
        h=self.login('patient@a.test',self.account['password'])
        self.assertEqual(self.client.post('/api/assistente',headers=h,json=question).status_code,403)

    def test_professionals_price_and_priority_endpoints_are_scoped(self):
        h=self.login('owner@a.test')
        self.assertEqual({p['nome'] for p in self.client.get('/api/profissionais').json()},{'Elias','Roberto'})
        with patch('app.create_llm') as llm:
            slots=self.client.post('/api/assistente',headers=h,json={'pergunta':'Quais os horários disponíveis do Roberto amanhã?'}).json()
            self.assertIn('Roberto',slots['resposta']);self.assertIn('minutos',slots['resposta']);llm.assert_not_called()
        aid=self.repo.list('attendance','a')[0]['id']
        from admin_actions import AdminActions,ToolPlan
        owner=self.repo.user('owner@a.test');service=AdminActions(self.repo,owner)
        d=service.prepare(ToolPlan(ferramenta='atendimento_atualizar',alvo=aid,dados={'prioridade':'urgente'}));service.confirm(d['id'],'confirmar')
        rows=self.client.get('/api/atendimentos').json();self.assertEqual(next(r for r in rows if r['id']==aid)['prioridade'],'urgente')
        self.login('owner@b.test');self.assertEqual(self.client.get('/api/profissionais').json(),[])
        self.assertEqual(self.client.get('/api/precos').json(),[])

    def test_booking_after_admin_tool_does_not_confirm_previous_action(self):
        from datetime import datetime,timedelta
        from management import LOCAL_ZONE
        h=self.login('owner@a.test')
        with patch('app.create_llm') as llm:
            llm.return_value.generate.return_value=json.dumps(dict(ferramenta='paciente_atualizar',alvo=self.patient['id'],dados={'telefone':'11999990000'}))
            self.client.post('/api/assistente',headers=h,json={'pergunta':'Atualize o telefone do Pedro para 11999990000'})
        self.client.post('/api/assistente',headers=h,json={'pergunta':'confirmar'})
        before=len(self.repo.list('appointments','a'))
        day=datetime.now(LOCAL_ZONE).date()+timedelta(days=8)
        while day.weekday()!=0:day+=timedelta(days=1)
        with patch('app.create_llm') as llm:
            self.client.post('/api/assistente',headers=h,json={'pergunta':f'Agende uma consulta para o Pedro dia {day.strftime("%d/%m/%Y")} às 11h'})
            ready=self.client.post('/api/assistente',headers=h,json={'pergunta':'limpeza'}).json()
            self.assertEqual(ready['estado'],'aguardando_confirmacao')
            result=self.client.post('/api/assistente',headers=h,json={'pergunta':'confirmar'}).json()
            self.assertEqual(result['estado'],'concluido')
            llm.assert_not_called()
        self.assertEqual(len(self.repo.list('appointments','a')),before+1)

    def test_resume_ai_and_priority_command_are_explicit_and_scoped(self):
        h=self.login('patient@a.test',self.account['password'])
        self.client.post('/api/cliente/mensagens',headers=h,json={'texto':'Falar com atendente','request_id':'handoff-0001'})
        self.assertEqual(self.client.get('/api/cliente/conversa').json()['status'],'escalated')
        self.assertEqual(self.client.post('/api/cliente/retomar').status_code,403)
        self.assertEqual(self.client.post('/api/cliente/retomar',headers=h).json()['status'],'pending')
        h=self.login('owner@a.test');aid=self.repo.list('attendance','a')[0]['id']
        with patch('app.create_llm') as llm:
            llm.return_value.generate.return_value=json.dumps(dict(ferramenta='atendimento_atualizar',alvo=aid,dados={'prioridade':'urgente'}))
            result=self.client.post('/api/assistente',headers=h,json={'pergunta':'Altere a prioridade do atendimento do Pedro para urgente'}).json()
            self.assertEqual(result['origem'],'operacao')
        self.client.post('/api/assistente',headers=h,json={'pergunta':'confirmar'})
        self.assertEqual(self.repo.list('attendance_meta','a')[0]['prioridade'],'urgente')

    def test_patient_confirmation_saves_in_owner_agenda_after_spaced_date(self):
        from datetime import datetime,timedelta
        from management import LOCAL_ZONE
        h=self.login('patient@a.test',self.account['password'])
        def send(text,key):
            r=self.client.post('/api/cliente/mensagens',headers=h,json={'texto':text,'request_id':key})
            self.assertEqual(r.status_code,200);return r.json()
        before=len(self.repo.list('appointments','a'))
        send('Quero marcar uma limpeza','booking-start-0001')
        day=datetime.now(LOCAL_ZONE).date()+timedelta(days=8)
        while day.weekday()!=0:day+=timedelta(days=1)
        text=f"pode ser dia {day.day} /{day.month}/{day.year} as 8:30"
        ready=send(text,'booking-choice-0001')
        self.assertEqual(ready['acao']['estado'],'aguardando_confirmacao')
        self.assertEqual(len(self.repo.list('appointments','a')),before)
        self.assertEqual(ready['mensagens'][-1]['acao']['estado'],'aguardando_confirmacao')
        done=send('confirmar','booking-confirm-0001')
        self.assertEqual(done['acao']['estado'],'concluido')
        appointment_id=done['acao']['agendamento_id']
        self.assertEqual(len(self.repo.list('appointments','a')),before+1)
        send('confirmar','booking-confirm-0001')
        self.assertEqual(len(self.repo.list('appointments','a')),before+1)
        self.login('owner@a.test')
        rows=self.client.get('/api/agendamentos').json()
        appointment=next(a for a in rows if a['id']==appointment_id)
        self.assertEqual(appointment['data'],day.isoformat())
        self.assertEqual(appointment['horario'],'08:30:00')
        self.assertEqual(appointment['dentista'],'Roberto')
        self.assertIn(str(appointment_id),self.client.get('/agendamentos').text)
