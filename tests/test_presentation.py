import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from persistence import SQLiteRepository
from seed_demo import seed
from prepare_clinic import prepare
from populate_conversations import populate
from enhance_clinic import enhance
from prepare_presentation import refresh
from knowledge_catalog import PROCEDURES,articles
from catalog import PROCEDURE_OPTIONS
from rag import LocalKeywordRetriever,AttendanceAgent
from unittest.mock import Mock


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.repo=SQLiteRepository(Path(self.tmp.name)/'db.sqlite3')
        self.repo.add_user(dict(email='owner@example.test',role='owner',empresa_id='a',empresa='a',password_hash='preserved-hash'))
        seed(self.repo,'a');prepare(self.repo,'a');enhance(self.repo,'a',date(2026,10,27));populate(self.repo,'a')

    def test_curated_articles_are_sourced_and_do_not_claim_clinic_fees(self):
        self.assertEqual(len(PROCEDURES),21)
        self.assertEqual(set(PROCEDURE_OPTIONS),{p.name for p in PROCEDURES})
        for article in articles():
            self.assertIn('https://',article['conteudo'])
            self.assertNotIn('FICTÍCIOS',article['conteudo'])
        refresh(self.repo,'a')
        for procedure in PROCEDURES:
            record=next(a for a in self.repo.list('kb','a') if a['titulo']==procedure.name)
            self.assertIn('não é preço fixo',record['conteudo'].lower())
            self.assertIn(procedure.source,record['conteudo'])
            self.assertIn(procedure.price,record['conteudo'])

    def test_refresh_preserves_ids_scope_contacts_and_is_idempotent(self):
        seed(self.repo,'b')
        other=copy.deepcopy(self.repo.list('patients','b'))
        before={kind:self.repo.list(kind,'a') for kind in ('patients','attendance','appointments','patient_links','stock')}
        user=self.repo.user('owner@example.test')
        result=refresh(self.repo,'a')
        self.assertEqual(result['artigos_criados'],21)
        self.assertEqual(len(self.repo.list('kb','a')),25)
        for kind,rows in before.items():
            updated=self.repo.list(kind,'a')
            self.assertEqual([r['id'] for r in rows],[r['id'] for r in updated])
        self.assertEqual(other,self.repo.list('patients','b'))
        for old,new in zip(before['patients'],self.repo.list('patients','a')):
            self.assertEqual(old['email'],new['email'])
            self.assertNotIn('Demonstração',new['nome'])
        after_user=self.repo.user('owner@example.test')
        self.assertEqual(user['password_hash'],after_user['password_hash'])
        self.assertEqual(after_user['empresa'],'Clínica SmartDent')
        for row in self.repo.list('attendance','a'):
            self.assertNotIn('Demonstração',row['cliente'])
            for message in row['mensagens']:
                self.assertNotIn('[Mensagem de exemplo]',message['texto'])
                self.assertNotIn('ORÇAMENTO SIMULADO',message['texto'])
        self.assertTrue(all(value==0 for value in refresh(self.repo,'a').values()))

    def test_quotation_summary_is_revised_without_claiming_model_generation(self):
        quote=next(a for a in self.repo.list('attendance','a') if a['cliente']=='Ana Demonstração')
        self.repo.set_summary('a',quote['id'],dict(resumo='Orçamento fictício com valores antigos',modelo='old',gerado_em='2026-10-27T00:00:00+00:00',versao='old'))
        refresh(self.repo,'a')
        from management import SummaryService
        summary=SummaryService(self.repo,'a').get(quote['id'])
        self.assertEqual(summary['modelo'],'revisao-editorial')
        self.assertFalse(summary['desatualizado'])
        self.assertIn('900,00',summary['resumo'])

    def test_specific_retrieval_and_context_after_expansion(self):
        refresh(self.repo,'a');retriever=LocalKeywordRetriever(self.repo)
        for question,title in [('Quanto custa um canal?','Tratamento de canal'),
                               ('Qual o valor do implante?','Implante dentário'),
                               ('Quanto custa a limpeza?','Limpeza dental (profilaxia)'),
                               ('Vocês fazem radiografia periapical?','Radiografia periapical'),
                               ('Qual o preço de um aparelho transparente?','Alinhadores transparentes')]:
            docs=retriever.retrieve('a',question)
            self.assertIn(title,{a['titulo'] for a in docs[:4]},question)
        for title in ['Horários de funcionamento e agendamento','Políticas, convênios e pagamento']:
            self.assertIn(title,{a['titulo'] for a in retriever.retrieve('a','Quais os horários e a política para remarcar?')})
        model=Mock();model.generate.return_value='Faixa informativa, sujeita a orçamento.'
        response=AttendanceAgent(retriever,model).answer('a','Quanto custa um canal?')
        self.assertTrue(response['gerado_por_llm'])
        self.assertIn('R$ 600,00 a R$ 2.500,00',str(model.generate.call_args))
        self.assertNotIn('DADOS FICTÍCIOS',str(model.generate.call_args))
        self.assertEqual(retriever.retrieve('b','valor de implante'),[])

    def test_missing_clinic_owner_rolls_back(self):
        original=self.repo.list('kb','a')
        with self.assertRaises(ValueError): refresh(self.repo,'missing')
        self.assertEqual(original,self.repo.list('kb','a'))
