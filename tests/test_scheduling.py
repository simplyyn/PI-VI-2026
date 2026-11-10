import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from persistence import SQLiteRepository
from services import Appointment, ClinicRecords, Patient
from scheduling import SchedulingAgent, AppointmentConflict
from management import LOCAL_ZONE


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/db.sqlite3'
        self.repo=SQLiteRepository(self.path)
        self.records=ClinicRecords(self.repo,'a')
        self.pedro=self.records.save('patients',Patient(nome='Pedro Silva'))
        self.session={}
        self.user=dict(id=1,empresa_id='a')
        self.now=datetime(2030,5,10,14,tzinfo=LOCAL_ZONE)

    def ask(self,text,session=None,user=None):
        return SchedulingAgent(self.repo,user or self.user,self.session if session is None else session,self.now).respond(text)

    def prepare(self):
        response=self.ask('Agende uma consulta para o Pedro Silva amanhã às 16h')
        self.assertIn('procedimento',response['resposta'])
        self.ask('Consulta de avaliação')
        self.ask('Dra. Ana')
        response=self.ask('30 minutos')
        self.assertEqual(response['estado'],'aguardando_confirmacao')
        self.assertIn('11/05/2030',response['resposta'])
        self.assertEqual(self.repo.list('appointments','a'),[])
        return response

    def test_collect_confirm_and_replay_across_repository_restart(self):
        self.prepare()
        pending=copy.deepcopy(self.session)
        result=self.ask('confirmar')
        self.assertEqual(result['estado'],'concluido')
        self.repo=SQLiteRepository(self.path)
        replay=self.ask('confirmar',pending)
        self.assertEqual(replay['agendamento_id'],result['agendamento_id'])
        self.assertEqual(len(self.repo.list('appointments','a')),1)
        self.assertEqual(self.ask('sim')['estado'],'concluido')
        self.assertEqual(len(self.repo.list('appointments','a')),1)

    def test_concurrent_confirmations_and_interleaving_manual_conflict(self):
        self.prepare()
        sessions=[copy.deepcopy(self.session) for _ in range(4)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda state:self.ask('confirmar',state),sessions))
        self.assertEqual(len({r['agendamento_id'] for r in results}),1)
        self.assertEqual(len(self.repo.list('appointments','a')),1)
        self.ask('Agende para o Pedro amanhã às 17h')
        self.ask('Consulta')
        self.ask('Dra. Ana')
        self.ask('30 minutos')
        self.records.save('appointments',Appointment(paciente_id=self.pedro['id'],data='2030-05-11',horario='17:15',duracao=30,procedimento='Retorno',dentista='Dra. Ana'))
        self.assertEqual(self.ask('confirmar')['estado'],'erro')
        self.assertEqual(len(self.repo.list('appointments','a')),2)

    def test_ambiguous_patient_expiration_cancellation_and_scope(self):
        other=self.records.save('patients',Patient(nome='Pedro Souza'))
        response=self.ask('Agende uma consulta para o Pedro amanhã às 16h')
        self.assertIn('mais de um',response['resposta'])
        self.assertEqual(self.ask(str(other['id']))['estado'],'coletando')
        self.assertEqual(self.session['booking']['data']['paciente_id'],other['id'])
        self.assertEqual(self.ask('cancelar')['estado'],'cancelado')
        self.assertEqual(self.repo.list('appointments','a'),[])
        self.prepare()
        self.assertIsNone(self.ask('confirmar',copy.deepcopy(self.session),dict(id=2,empresa_id='b')))
        self.session['booking']['time']-=1801
        self.assertIsNone(self.ask('confirmar'))

    def test_correct_time_and_doctor_before_confirmation(self):
        self.prepare()
        response=self.ask('mude para as 17h')
        self.assertEqual(response['estado'],'aguardando_confirmacao')
        self.assertIn('17:00',response['resposta'])
        response=self.ask('dentista Dra. Beatriz')
        self.assertIn('Beatriz',response['resposta'])
        self.ask('confirmar')
        self.assertEqual(self.repo.list('appointments','a')[0]['horario'],'17:00:00')

    def test_day_after_tomorrow_is_not_tomorrow(self):
        self.prepare()
        result=self.ask('depois de amanhã às 10h')
        self.assertEqual(result['estado'],'aguardando_confirmacao')
        self.assertEqual(self.session['booking']['data']['data'],'2030-05-12')

    def test_manual_conflicts_status_edits_and_cross_clinic(self):
        data=dict(paciente_id=self.pedro['id'],data='2030-05-11',horario='16:00',duracao=30,procedimento='Avaliação',dentista='Dra. Ana')
        first=self.records.save('appointments',Appointment(**data))
        with self.assertRaises(AppointmentConflict):
            self.records.save('appointments',Appointment(**dict(data,horario='16:15',dentista='ANA')))
        self.records.save('appointments',Appointment(**dict(data,horario='16:30')))
        self.records.save('appointments',Appointment(**dict(data,status='cancelado')))
        self.records.save('appointments',Appointment(**dict(data,horario='15:30')),first['id'])
        with self.assertRaises(LookupError):
            ClinicRecords(self.repo,'b').save('appointments',Appointment(**data))
        with self.assertRaises(AppointmentConflict):
            self.records.save('appointments',Appointment(**dict(data,horario='23:50')))

    def test_deleted_receipt_does_not_recreate_and_llm_not_required(self):
        self.prepare()
        pending=copy.deepcopy(self.session)
        done=self.ask('confirmar')
        self.records.delete('appointments',done['agendamento_id'])
        self.assertEqual(self.ask('confirmar',pending)['estado'],'erro')
        self.assertEqual(self.repo.list('appointments','a'),[])

    def test_postgres_action_is_explicitly_unavailable_without_schema_change(self):
        self.repo.supports_booking_receipts=False
        self.assertEqual(self.ask('agende uma consulta')['estado'],'indisponivel')
        self.assertEqual(self.repo.list('appointments','a'),[])

    def test_invalid_past_time_and_inactive_patient(self):
        self.prepare()
        self.assertEqual(self.ask('hoje às 10h')['estado'],'erro')
        self.assertEqual(self.ask('amanhã às 99h')['estado'],'erro')
        self.assertEqual(self.ask('amanhã às 16h')['estado'],'aguardando_confirmacao')
        self.records.save('patients',Patient(nome='Pedro Silva',status='inativo'),self.pedro['id'])
        self.assertEqual(self.ask('confirmar')['estado'],'erro')
        self.assertEqual(self.repo.list('appointments','a'),[])

    def test_procedure_in_initial_message_and_queries_after_completion(self):
        response=self.ask('Agende limpeza para o Pedro amanhã às 16h')
        self.assertIn('profissional',response['resposta'])
        self.ask('Dra. Ana');self.ask('30 minutos');self.ask('confirmar')
        self.assertIsNone(self.ask('agenda de amanhã'))
        self.assertEqual(len(self.repo.list('appointments','a')),1)
