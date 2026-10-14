"""Mesmo contrato de repositório verificado no SQLite (sempre) e no PostgreSQL (com SMARTDENT_TEST_DATABASE_URL)."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from persistence import SQLiteRepository
from pg_support import URL, SKIP_REASON, FakeEmbedder, fresh_database

STAMP = '2026-10-14T12:00:00+00:00'
SAMPLES = {
    'kb': dict(titulo='Artigo fictício', categoria='Teste', conteudo='Conteúdo fictício', status=True, views=0, atualizado='14/10/2026'),
    'stock': dict(nome='Item fictício', categoria='EPI', unidade='un', quantidade=2, minimo=1),
    'patients': dict(nome='Paciente Teste', telefone='000', email='paciente@example.test', status='novo', plano='Particular',
                     ultima_consulta=None, proxima_consulta='2026-10-20', procedimentos=1, iniciais='PT', cor='#0284c7', criado_em=STAMP),
    'attendance': dict(cliente='Cliente Teste', preview='Assunto fictício', status='pending', canal='human', iniciais='CT', cor='',
                       hora='10:00', mensagens=[], criado_em=STAMP),
}
EDITABLE = {'kb':'titulo','stock':'nome','patients':'nome','appointments':'procedimento','attendance':'cliente'}

class RepositoryContract:
    def make_repository(self):
        raise NotImplementedError

    def setUp(self):
        self.repo = self.make_repository()
        for email, clinic in [('a@example.test','a'),('b@example.test','b')]:
            self.repo.add_user(dict(email=email,nome='Teste',iniciais='TT',role='owner',empresa_id=clinic,password_hash='hash-ficticio'))

    def test_users(self):
        user = self.repo.user(' A@Example.test ')
        self.assertEqual((user['email'],user['role'],user['empresa_id']),('a@example.test','owner','a'))
        self.assertEqual(self.repo.user_by_id(user['id'])['email'],'a@example.test')
        self.assertIsNone(self.repo.user('ausente@example.test'))
        self.assertIsNone(self.repo.user_by_id(999999))
        with self.assertRaises(ValueError):
            self.repo.add_user(dict(email='A@example.test',role='owner',empresa_id='a',password_hash='hash-ficticio'))
        admin = self.repo.add_user(dict(email='admin@example.test',nome='Admin',role='admin',empresa_id='',password_hash='hash-ficticio'))
        self.assertEqual(self.repo.user_by_id(admin['id'])['empresa_id'],'')

    def test_crud_roundtrip_and_isolation(self):
        patient = self.repo.save('patients','a',SAMPLES['patients'])
        samples = dict(SAMPLES,appointments=dict(paciente_id=patient['id'],data='2026-10-14',horario='10:30:00',duracao=30,
                                                 procedimento='Avaliação',dentista='Dra. Teste',status='pendente',cor='#0284c7',criado_em=STAMP))
        for kind,data in samples.items():
            with self.subTest(kind=kind):
                record = patient if kind == 'patients' else self.repo.save(kind,'a',data)
                self.assertEqual({k:v for k,v in record.items() if k != 'id'},data)
                self.assertEqual(self.repo.list(kind,'a'),[record])
                self.assertEqual(self.repo.list(kind,'b'),[])
                changed = dict(data,**{EDITABLE[kind]:'Editado'})
                with self.assertRaises(LookupError): self.repo.save(kind,'b',changed,record['id'])
                with self.assertRaises(LookupError): self.repo.delete(kind,'b',record['id'])
                self.assertEqual(self.repo.save(kind,'a',changed,record['id']),dict(changed,id=record['id']))
                self.assertEqual(self.repo.list(kind,'a'),[dict(changed,id=record['id'])])
        for kind in ['appointments','patients','kb','stock','attendance']:
            identifier = self.repo.list(kind,'a')[0]['id']
            self.repo.delete(kind,'a',identifier)
            self.assertEqual(self.repo.list(kind,'a'),[])
            with self.assertRaises(LookupError): self.repo.delete(kind,'a',identifier)

    def test_concurrent_stock_moves_are_atomic(self):
        item = self.repo.save('stock','a',SAMPLES['stock'])
        with self.assertRaises(ValueError): self.repo.move('a',item['id'],-3)
        with self.assertRaises(LookupError): self.repo.move('b',item['id'],1)
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda _: self.repo.move('a',item['id'],1),range(40)))
        self.assertEqual(self.repo.list('stock','a')[0]['quantidade'],42)

    def test_messages_and_complaints(self):
        attendance = self.repo.save('attendance','a',SAMPLES['attendance'])
        message = dict(texto='Resposta humana fictícia',autor='human',criado_em='2026-10-14T12:05:00+00:00')
        self.assertEqual(self.repo.append_message('a',attendance['id'],message)['mensagens'],[message])
        with self.assertRaises(LookupError): self.repo.append_message('b',attendance['id'],message)
        updated = self.repo.save('attendance','a',dict(SAMPLES['attendance'],status='resolved'),attendance['id'])
        self.assertEqual(updated['mensagens'],[message])
        verdict = dict(reclamacao=True,categoria='atendimento',motivo='Demora na resposta',origem='manual',modelo='',
                       classificado_em='2026-10-14T12:10:00+00:00')
        first = self.repo.set_complaint('a',attendance['id'],verdict)
        second = self.repo.set_complaint('a',attendance['id'],dict(verdict,reclamacao=False,categoria=None,origem='ia'))
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.repo.list('complaints','a'),
                         [dict(verdict,reclamacao=False,categoria=None,origem='ia',attendance_id=attendance['id'],id=first['id'])])
        self.assertEqual(self.repo.list('complaints','b'),[])
        with self.assertRaises(LookupError): self.repo.set_complaint('b',attendance['id'],verdict)
        with self.assertRaises(LookupError): self.repo.set_complaint('a',999999,verdict)
        with self.assertRaises(LookupError): self.repo.delete_complaint('b',attendance['id'])
        self.repo.delete('attendance','a',attendance['id'])
        self.assertEqual(self.repo.list('complaints','a'),[])

class SQLiteContractTests(RepositoryContract, unittest.TestCase):
    def make_repository(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return SQLiteRepository(tmp.name+'/contrato.sqlite3')

@unittest.skipUnless(URL, SKIP_REASON)
class PostgresContractTests(RepositoryContract, unittest.TestCase):
    def make_repository(self):
        from postgres import PostgresRepository
        repo = PostgresRepository(fresh_database(self),embedder=FakeEmbedder())
        self.addCleanup(repo.close)
        return repo

if __name__ == '__main__': unittest.main()
