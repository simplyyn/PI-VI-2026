import copy
import json
import unittest
from datetime import datetime,timedelta
from management import LOCAL_ZONE
from professionals import Professional
from repair_professionals import repair
import test_integrated_api


class ProfessionalPageTests(unittest.TestCase):
    password='profile-test-password'
    @classmethod
    def setUpClass(cls):
        from auth import hash_password
        cls.hashed=hash_password(cls.password)
    setUp=test_integrated_api.IntegratedAPITests.setUp
    login=test_integrated_api.IntegratedAPITests.login
    database_url=test_integrated_api.IntegratedAPITests.database_url

    def test_page_two_professionals_and_agenda_links(self):
        h=self.login('owner@a.test')
        response=self.client.get('/profissionais')
        self.assertEqual(response.status_code,200)
        self.assertIn('Elias',response.text);self.assertIn('Roberto',response.text)
        self.assertIn('2 profissionais cadastrados',response.text)
        for p in self.repo.list('professionals','a'):
            self.assertIn('/agendamentos?profissional_id='+str(p['id']),response.text)
        agenda=self.client.get('/agendamentos').text
        self.assertIn('id="agenda-professional"',agenda)
        self.login('owner@b.test')
        self.assertNotIn('data-edit-professional=',self.client.get('/profissionais').text)
        self.login('patient@a.test',self.account['password'])
        self.assertEqual(self.client.get('/profissionais',follow_redirects=False).status_code,302)

    def test_update_validation_scope_csrf_and_existing_bookings(self):
        h=self.login('owner@a.test');p=next(p for p in self.repo.list('professionals','a') if p['nome']=='Roberto')
        route='/api/profissionais/'+str(p['id'])
        data={k:v for k,v in p.items() if k!='id'}
        self.assertEqual(self.client.put(route,json=data).status_code,403)
        altered=dict(data,especialidades=['Prevenção','Clínica geral','Acompanhamento preventivo'])
        self.assertEqual(self.client.put(route,headers=h,json=altered).status_code,200)
        invalid=dict(data,expediente={'0':[['12:00','08:00']]})
        self.assertEqual(self.client.put(route,headers=h,json=invalid).status_code,422)
        self.assertEqual(self.client.put(route,headers=h,json=dict(data,ativo=False)).status_code,409)
        self.assertEqual(self.client.put(route,headers=h,json=dict(data,expediente={})).status_code,409)
        self.assertEqual(self.client.put(route,headers=h,json=dict(data,nome='Elias')).status_code,409)
        h=self.login('owner@b.test')
        self.assertEqual(self.client.put(route,headers=h,json=altered).status_code,404)
        h=self.login('patient@a.test',self.account['password'])
        self.assertEqual(self.client.put(route,headers=h,json=altered).status_code,403)

    def test_renaming_updates_cached_appointment_names_without_losing_data(self):
        h=self.login('owner@a.test');p=next(p for p in self.repo.list('professionals','a') if p['nome']=='Roberto')
        before=[a for a in self.repo.list('appointments','a') if a.get('profissional_id')==p['id']]
        data={k:v for k,v in p.items() if k!='id'};data['nome']='Roberto Silva'
        r=self.client.put('/api/profissionais/'+str(p['id']),headers=h,json=data)
        self.assertEqual(r.status_code,200)
        after=[a for a in self.repo.list('appointments','a') if a.get('profissional_id')==p['id']]
        for a,b in zip(before,after):
            self.assertEqual(b['dentista'],'Roberto Silva')
            self.assertEqual({k:v for k,v in a.items() if k!='dentista'},{k:v for k,v in b.items() if k!='dentista'})

    def test_legacy_reassignment_preserves_history_and_is_idempotent(self):
        past=datetime.now(LOCAL_ZONE).date()-timedelta(days=10)
        legacy=[]
        for i,procedure in enumerate(['Consulta de avaliação','Limpeza dental (profilaxia)','Avaliação ortodôntica','Restauração dentária','limpeza']):
            data=dict(paciente_id=self.patient['id'],data=past.isoformat(),horario=f'{8+i}:00:00',duracao=30,procedimento=procedure,dentista='Dra. Marina' if i<4 else 'caio',status='confirmado',cor='#0284c7',criado_em='2026-10-01T00:00:00+00:00')
            with self.repo.connect() as db:
                identifier=db.execute("INSERT INTO records(kind,clinic,data) VALUES ('appointments','a',?)",(json.dumps(data),)).lastrowid
            legacy.append(dict(data,id=identifier))
        self.assertEqual(repair(self.repo,'a')['consultas_reassociadas'],5)
        by_id={r['id']:r for r in self.repo.list('appointments','a')}
        for old in legacy:
            new=by_id[old['id']]
            self.assertIn(new['dentista'],('Elias','Roberto'))
            self.assertIsNotNone(new['profissional_id'])
            for key in ('paciente_id','data','horario','duracao','procedimento','status'):self.assertEqual(new[key],old[key])
        self.assertEqual(len(self.repo.list('appointment_reassignments','a')),5)
        self.assertEqual(repair(self.repo,'a')['consultas_reassociadas'],0)
