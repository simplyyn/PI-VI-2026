import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from unittest.mock import Mock
from persistence import SQLiteRepository
from services import Patient,ClinicRecords,Appointment
from workflows import CustomerChat,BatchReplies,WorkflowConflict,pending,deliver,record,waiting_messages
from prepare_integrated import prepare
from professionals import available,PatientBooking
from admin_actions import AdminActions,ToolPlan
from management import LOCAL_ZONE
from llm import LLMUnavailable


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.repo=SQLiteRepository(self.tmp.name+'/db.sqlite3')
        self.owner=self.repo.add_user(dict(email='owner@a.test',role='owner',empresa_id='a'))
        self.patient=ClinicRecords(self.repo,'a').save('patients',Patient(nome='Pedro Silva',status='ativo'))
        account=prepare(self.repo,'a',self.patient['id'],'pedro@a.test')
        self.user=self.repo.user('pedro@a.test');self.chat=CustomerChat(self.repo,self.user)
        self.aid=self.chat.get()['atendimento_id']
        self.generator=Mock(return_value=dict(resposta='Mensagem contextualizada',gerado_por_llm=True))

    def test_patient_and_owner_communication_idempotency_and_waiting_counts(self):
        self.chat.send('Qual o preço?', 'message-0001',self.generator,False)
        self.generator.assert_not_called()
        p=pending(self.repo,'a');self.assertEqual((p['conversas'],p['mensagens']),(1,1))
        self.chat.send('Qual o preço?', 'message-0001',self.generator,False)
        self.assertEqual(pending(self.repo,'a')['mensagens'],1)
        deliver(self.repo,self.owner,self.aid,'A limpeza custa conforme avaliação.','owner-0001')
        self.assertEqual(pending(self.repo,'a')['mensagens'],0)
        self.assertEqual(self.chat.get()['mensagens'][-1]['autor'],'human')
        self.chat.send('Obrigado', 'message-0002',self.generator,False)
        self.assertEqual(pending(self.repo,'a')['mensagens'],1)
        self.assertEqual(pending(self.repo,'b')['mensagens'],0)
        with self.assertRaises(WorkflowConflict):self.chat.send('Outro texto','message-0001',self.generator)

    def test_model_failure_keeps_message_pending_and_does_not_fake_reply(self):
        broken=Mock(side_effect=LLMUnavailable('Sem cota'))
        data=self.chat.send('Tenho uma pergunta','failure-0001',broken)
        self.assertIn('salva',data['aviso'])
        self.assertEqual(len(data['mensagens']),1)
        self.assertEqual(pending(self.repo,'a')['mensagens'],1)
        self.chat.send('Tenho uma pergunta','failure-0001',broken)
        broken.assert_called_once()

    def test_concurrent_duplicate_requests_generate_once_and_stale_ai_is_discarded(self):
        entered=threading.Event();release=threading.Event()
        def answer(*args):entered.set();release.wait(5);return dict(resposta='Sugestão atrasada',gerado_por_llm=True)
        with ThreadPoolExecutor(2) as pool:
            first=pool.submit(self.chat.send,'Olá','concurrent-0001',answer)
            self.assertTrue(entered.wait(5))
            duplicate=pool.submit(self.chat.send,'Olá','concurrent-0001',answer)
            result=duplicate.result(timeout=5);self.assertEqual(len(result['mensagens']),1)
            deliver(self.repo,self.owner,self.aid,'Resposta humana antes da IA','human-0001')
            release.set();first.result(timeout=5)
        messages=self.chat.get()['mensagens']
        self.assertEqual(len(messages),2)
        self.assertNotIn('Sugestão atrasada',str(messages))

    def test_batch_is_preview_only_reusable_and_confirmed_idempotently(self):
        self.chat.send('Olá','batch-0001',self.generator,False)
        service=BatchReplies(self.repo,self.owner)
        draft=service.prepare(lambda *args:dict(resposta='Resposta para revisão',gerado_por_llm=True))
        before=len(self.chat.get()['mensagens'])
        again=service.prepare(Mock(side_effect=AssertionError('Não deveria gerar de novo')))
        self.assertEqual(draft['id'],again['id'])
        self.assertEqual(len(self.chat.get()['mensagens']),before)
        items=[dict(id=self.aid,texto='Texto revisado pelo responsável')]
        self.assertEqual(service.send(draft['id'],items)['enviados'],1)
        service.send(draft['id'],items)
        self.assertEqual(len(self.chat.get()['mensagens']),before+1)
        self.assertEqual(pending(self.repo,'a')['conversas'],0)
        changed=service.send(draft['id'],[dict(id=self.aid,texto='Texto alterado após envio')])
        self.assertEqual(changed['enviados'],0)

    def test_batch_detects_new_message_partial_failure_and_cross_owner(self):
        self.chat.send('Olá','batch-stale1',self.generator,False)
        service=BatchReplies(self.repo,self.owner)
        draft=service.prepare(Mock(side_effect=LLMUnavailable('Cota')))
        self.assertTrue(draft['items'][0]['erro'])
        self.chat.send('Outra pergunta','batch-stale2',self.generator,False)
        result=service.send(draft['id'],[dict(id=self.aid,texto='Resposta da prévia antiga')])
        self.assertEqual(result['enviados'],0)
        self.assertEqual(result['resultados'][0]['status'],'revisar')
        other=dict(self.owner,id=999)
        with self.assertRaises(LookupError):BatchReplies(self.repo,other).get(draft['id'])
        with self.assertRaises(WorkflowConflict):BatchReplies(self.repo,self.user)

    def test_structured_professionals_enforce_hours_specialty_and_patient_conflicts(self):
        profiles=self.repo.list('professionals','a');roberto=next(p for p in profiles if p['nome']=='Roberto');elias=next(p for p in profiles if p['nome']=='Elias')
        monday=datetime.now(LOCAL_ZONE).date()+timedelta(days=8)
        while monday.weekday()!=0:monday+=timedelta(days=1)
        data=dict(paciente_id=self.patient['id'],data=monday.isoformat(),horario='09:00',duracao=30,procedimento='Limpeza dental (profilaxia)',dentista='Roberto',profissional_id=roberto['id'])
        records=ClinicRecords(self.repo,'a');records.save('appointments',Appointment(**data))
        with self.assertRaises(ValueError):records.save('appointments',Appointment(**dict(data,horario='19:00')))
        with self.assertRaises(ValueError):records.save('appointments',Appointment(**dict(data,procedimento='Implante dentário')))
        self.assertNotIn('09:00',available(self.repo,'a',roberto['id'],monday.isoformat(),30))
        self.assertNotIn('09:00',available(self.repo,'a',elias['id'],monday.isoformat(),60,self.patient['id']))
        with self.assertRaises(ValueError):records.save('appointments',Appointment(**dict(data,profissional_id=elias['id'])))

    def test_patient_scheduler_binds_identity_and_surgery_means_assessment(self):
        session={};scheduler=PatientBooking(self.repo,self.user,session)
        response=scheduler.answer('Quero marcar uma cirurgia super complicada no dente')
        self.assertIn('Elias',response['resposta']);self.assertIn('avaliação',response['resposta'].lower())
        self.assertEqual(session['patient_booking']['procedure'],'Avaliação cirúrgica')
        monday=datetime.now(LOCAL_ZONE).date()+timedelta(days=8)
        while monday.weekday()!=0:monday+=timedelta(days=1)
        response=scheduler.answer(monday.strftime('%d/%m/%Y')+' às 10h')
        self.assertEqual(response['estado'],'aguardando_confirmacao')
        self.assertEqual(session['booking']['data']['paciente_id'],self.patient['id'])
        created=scheduler.answer('confirmar')
        self.assertEqual(created['estado'],'concluido')
        record_created=record(self.repo,'appointments','a',created['agendamento_id'])
        self.assertEqual(record_created['dentista'],'Elias')
        self.assertEqual(record_created['procedimento'],'Avaliação cirúrgica')

    def test_admin_tools_review_confirmation_audit_and_snapshot_conflict(self):
        service=AdminActions(self.repo,self.owner)
        draft=service.prepare(ToolPlan(ferramenta='paciente_atualizar',alvo=self.patient['id'],dados={'telefone':'11999990000'}))
        self.assertEqual(ClinicRecords(self.repo,'a').get('patients',self.patient['id'])['telefone'],'')
        service.confirm(draft['id'],'confirmar');service.confirm(draft['id'],'confirmar')
        self.assertEqual(ClinicRecords(self.repo,'a').get('patients',self.patient['id'])['telefone'],'11999990000')
        self.assertEqual(len(self.repo.list('action_receipts','a')),1)
        self.assertTrue(self.repo.list('audit','a'))
        draft=service.prepare(ToolPlan(ferramenta='paciente_atualizar',alvo=self.patient['id'],dados={'telefone':'11888880000'}))
        row=record(self.repo,'patients','a',self.patient['id']);row.pop('id');row['telefone']='11777770000';self.repo.save('patients','a',row,self.patient['id'])
        with self.assertRaises(WorkflowConflict):service.confirm(draft['id'],'confirmar')
        with self.assertRaises(WorkflowConflict):AdminActions(self.repo,self.user)

    def test_admin_price_priority_stock_and_knowledge_tools(self):
        service=AdminActions(self.repo,self.owner)
        with self.assertRaises(WorkflowConflict):service.prepare(ToolPlan(ferramenta='preco_definir',alvo='Limpeza dental (profilaxia)',dados={'centavos':6000,'anterior_centavos':5000}))
        for plan in [ToolPlan(ferramenta='preco_definir',alvo='Limpeza dental (profilaxia)',dados={'centavos':6000,'unidade':'por sessão'}),ToolPlan(ferramenta='atendimento_atualizar',alvo=self.aid,dados={'prioridade':'urgente','revisado':True}),ToolPlan(ferramenta='estoque_cadastrar',dados={'nome':'Luvas','categoria':'EPI','unidade':'caixa','quantidade':10,'minimo':2}),ToolPlan(ferramenta='conhecimento_cadastrar',dados={'titulo':'Pagamento','categoria':'Regras','conteudo':'Pix aceito.'})]:
            d=service.prepare(plan);service.confirm(d['id'],'confirmar')
        self.assertEqual(self.repo.list('prices','a')[0]['centavos'],6000)
        stock=self.repo.list('stock','a')[0]
        d=service.prepare(ToolPlan(ferramenta='estoque_movimentar',alvo=stock['id'],dados={'delta':-2}));service.confirm(d['id'],'confirmar')
        self.assertEqual(self.repo.list('stock','a')[0]['quantidade'],8)
        self.assertEqual(self.repo.list('attendance_meta','a')[0]['prioridade'],'urgente')
        from rag import LocalKeywordRetriever
        self.assertIn('PREÇO PRÓPRIO',str(LocalKeywordRetriever(self.repo).retrieve('a','Qual o preço da limpeza?')))

    def test_delete_requires_specific_confirmation_and_transaction_rolls_back(self):
        service=AdminActions(self.repo,self.owner)
        stock=self.repo.save('stock','a',dict(nome='Luvas',categoria='EPI',unidade='caixa',quantidade=1,minimo=1))
        d=service.prepare(ToolPlan(ferramenta='registro_excluir',alvo=stock['id'],dados={'tipo':'estoque'}))
        with self.assertRaises(WorkflowConflict):service.confirm(d['id'],'confirmar')
        service.confirm(d['id'],f"EXCLUIR {stock['id']}")
        self.assertEqual(self.repo.list('stock','a'),[])
        with self.assertRaises(RuntimeError):
            with self.repo.transaction() as tx:
                tx.save('kb','a',dict(titulo='Não deve persistir'));raise RuntimeError()
        self.assertEqual(self.repo.list('kb','a'),[])

    def test_batch_partial_success_and_concurrent_admin_confirmation(self):
        self.chat.send('Primeira dúvida','partial-first',self.generator,False)
        second=ClinicRecords(self.repo,'a').save('attendance',__import__('services').Attendance(cliente='Outro paciente',preview='Dúvida'))
        self.repo.append_message('a',second['id'],dict(autor='client',texto='Segunda dúvida',criado_em=__import__('workflows').now()))
        batch=BatchReplies(self.repo,self.owner);draft=batch.prepare(lambda *a:dict(resposta='Resposta para revisão'))
        self.repo.append_message('a',second['id'],dict(autor='client',texto='Complemento novo',criado_em=__import__('workflows').now()))
        result=batch.send(draft['id'],[dict(id=r['id'],texto='Resposta revisada') for r in draft['items']])
        self.assertEqual(result['enviados'],1)
        self.assertEqual({r['status'] for r in result['resultados']},{'enviado','revisar'})
        service=AdminActions(self.repo,self.owner)
        d=service.prepare(ToolPlan(ferramenta='paciente_atualizar',alvo=self.patient['id'],dados={'telefone':'11999990000'}))
        with ThreadPoolExecutor(4) as pool:
            results=list(pool.map(lambda _:AdminActions(self.repo,self.owner).confirm(d['id'],'confirmar'),range(4)))
        self.assertEqual(len(self.repo.list('action_receipts','a')),1)
        self.assertEqual(sum('já foi processada' in r['resposta'] for r in results),3)

    def test_appointment_tools_and_individual_portal_delivery(self):
        service=AdminActions(self.repo,self.owner)
        appointment=next(a for a in self.repo.list('appointments','a') if a['dentista']=='Roberto')
        day=datetime.now(LOCAL_ZONE).date()+timedelta(days=8)
        while day.weekday()!=0:day+=timedelta(days=1)
        draft=service.prepare(ToolPlan(ferramenta='consulta_atualizar',alvo=appointment['id'],dados={'data':day.isoformat(),'horario':'10:30'}))
        service.confirm(draft['id'],'confirmar')
        self.assertEqual(record(self.repo,'appointments','a',appointment['id'])['data'],day.isoformat())
        draft=service.prepare(ToolPlan(ferramenta='consulta_atualizar',alvo=appointment['id'],dados={'status':'cancelado'}))
        service.confirm(draft['id'],'confirmar')
        self.assertEqual(record(self.repo,'appointments','a',appointment['id'])['status'],'cancelado')
        self.chat.send('Preciso de ajuda','individual-msg1',self.generator,False)
        draft=service.prepare(ToolPlan(ferramenta='mensagem_enviar',alvo=self.aid,dados={'texto':'Olá, Pedro. Vamos conferir seu horário.'}))
        service.confirm(draft['id'],'confirmar')
        self.assertEqual(self.chat.get()['mensagens'][-1]['texto'],'Olá, Pedro. Vamos conferir seu horário.')
        self.assertEqual(pending(self.repo,'a')['mensagens'],0)
