"""Testes específicos do PostgreSQL/pgvector. Exigem SMARTDENT_TEST_DATABASE_URL (banco descartável)."""
import os
import unittest
from unittest.mock import patch
import test_api
from pg_support import URL, SKIP_REASON, FakeEmbedder, fresh_database

@unittest.skipUnless(URL, SKIP_REASON)
class PostgresTests(unittest.TestCase):
    def setUp(self):
        from postgres import PostgresRepository
        self.url = fresh_database(self)
        self.embedder = FakeEmbedder()
        self.repo = PostgresRepository(self.url,embedder=self.embedder)
        self.addCleanup(self.repo.close)
        for clinic in 'ab':
            self.repo.add_user(dict(email=f'{clinic}@example.test',role='owner',empresa_id=clinic,password_hash='hash-ficticio'))

    def article(self,clinic,titulo,conteudo,status=True,identifier=None):
        return self.repo.save('kb',clinic,dict(titulo=titulo,categoria='Teste',conteudo=conteudo,status=status,views=0,atualizado='14/10/2026'),identifier)

    def chunks(self,article_id):
        with self.repo._transaction() as conn:
            return conn.execute('SELECT ordem, conteudo, modelo FROM kb_chunks WHERE article_id = %s ORDER BY ordem',(article_id,)).fetchall()

    def test_migrations_are_tracked_and_idempotent(self):
        from postgres import migrate
        self.assertEqual(migrate(self.url),[])
        with self.repo._transaction() as conn:
            self.assertEqual([r['versao'] for r in conn.execute('SELECT versao FROM schema_migrations')],['001_schema'])
            tables = {r['table_name'] for r in conn.execute('SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()')}
        self.assertLessEqual({'clinics','users','kb_articles','kb_chunks','stock_items','stock_movements','patients','appointments',
                              'attendances','attendance_messages','complaint_classifications'},tables)

    def test_semantic_search_is_isolated_and_ignores_inactive(self):
        alvo = self.article('a','Clareamento dental','Clareamento a laser custa oitocentos reais')
        self.article('a','Horário','Atendimento de segunda a sexta')
        inativo = self.article('a','Clareamento antigo','Clareamento promocional encerrado',status=False)
        self.article('b','Clareamento clínica B','Clareamento secreto da outra clínica')
        results = self.repo.search_knowledge('a','Quanto custa o clareamento?')
        self.assertEqual(results[0]['id'],alvo['id'])
        self.assertLess(results[0]['distancia'],self.repo.max_distance)
        self.assertTrue(all(r['empresa_id']=='a' for r in results))
        self.assertNotIn(inativo['id'],[r['id'] for r in results])
        self.assertNotIn('secreto',str(results))
        self.assertEqual(self.repo.search_knowledge('a','pizza futebol'),[])

    def test_index_follows_updates_deletes_and_long_articles(self):
        long_text = ' '.join(f'Frase número {i} sobre higiene bucal.' for i in range(200))+' '+' '.join(['Implante de zircônia exige avaliação prévia.']*8)
        article = self.article('a','Guia longo',long_text)
        chunks = self.chunks(article['id'])
        self.assertGreater(len(chunks),5)
        self.assertTrue(all(len(c['conteudo'])<=600 and c['modelo']==FakeEmbedder.model for c in chunks))
        result = self.repo.search_knowledge('a','zircônia implante')[0]
        self.assertIn('zircônia',result['conteudo'])
        self.assertLess(len(result['conteudo']),len(long_text))
        calls = self.embedder.calls
        self.article('a','Guia longo',long_text,status=False,identifier=article['id'])
        self.assertEqual(self.embedder.calls,calls)
        self.article('a','Guia curto','Texto novo sobre aparelho ortodôntico',identifier=article['id'])
        self.assertEqual([c['conteudo'] for c in self.chunks(article['id'])],['Texto novo sobre aparelho ortodôntico'])
        self.repo.delete('kb','a',article['id'])
        self.assertEqual(self.chunks(article['id']),[])

    def test_embedding_failure_keeps_article_and_reindex_recovers(self):
        self.repo.embedder = FakeEmbedder(fail=True)
        with self.assertLogs('smartdent.postgres','WARNING'):
            article = self.article('a','Convênios','Aceitamos Unimed fictício')
        self.assertEqual(self.chunks(article['id']),[])
        self.assertEqual(self.repo.list('kb','a')[0]['conteudo'],'Aceitamos Unimed fictício')
        self.repo.embedder = FakeEmbedder()
        self.assertEqual(self.repo.reindex(),1)
        self.assertEqual(len(self.chunks(article['id'])),1)
        self.assertEqual(self.repo.reindex(),0)
        self.assertEqual(self.repo.reindex(force=True),1)

    def test_stock_history_and_cross_clinic_foreign_keys(self):
        item = self.repo.save('stock','a',dict(nome='Luvas',categoria='EPI',unidade='cx',quantidade=2,minimo=1))
        self.repo.move('a',item['id'],3)
        self.repo.move('a',item['id'],-1)
        with self.repo._transaction() as conn:
            history = conn.execute('SELECT delta, saldo FROM stock_movements WHERE stock_item_id = %s ORDER BY id',(item['id'],)).fetchall()
        self.assertEqual([(h['delta'],h['saldo']) for h in history],[(3,5),(-1,4)])
        patient_b = self.repo.save('patients','b',dict(nome='Paciente B'))
        with self.assertRaises(ValueError):
            self.repo.save('appointments','a',dict(paciente_id=patient_b['id'],data='2026-10-14',horario='10:00:00',duracao=30,procedimento='x',dentista='y'))
        with self.assertRaises(TypeError):
            self.repo.save('stock','a',dict(item,campo_inexistente=1))

@unittest.skipUnless(URL, SKIP_REASON)
class PostgresAPITests(test_api.APITests):
    """Toda a suíte HTTP de test_api rodando sobre o PostgreSQL."""
    def environment(self):
        return dict(super().environment(),SMARTDENT_DATABASE_URL=fresh_database(self),SMARTDENT_EMBEDDINGS='off')

    def test_pgvector_search_endpoint_and_chat(self):
        from app import app
        app.state.repository.embedder = FakeEmbedder()
        headers = self.login()
        data = dict(titulo='Clareamento dental',categoria='Estética',conteudo='Clareamento a laser custa oitocentos reais',status=True)
        self.assertEqual(self.client.post('/api/base-conhecimento',json=data,headers=headers).status_code,201)
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':'pgvector'}):
            results = self.client.get('/api/base-conhecimento/busca',params={'q':'quanto custa clareamento'}).json()
            self.assertEqual(results[0]['titulo'],data['titulo'])
            self.assertIsNotNone(results[0]['distancia'])
            with patch('app.GroqClient') as model:
                model.return_value.generate.return_value = 'Resposta simulada'
                body = self.client.post('/api/chat',json={'pergunta':'quanto custa clareamento'},headers=headers).json()
            self.assertTrue(body['gerado_por_llm'])
            self.assertEqual(body['fontes'][0]['titulo'],data['titulo'])
            self.login('b@example.test')
            self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':'quanto custa clareamento'}).json(),[])
            app.state.repository.embedder = None
            self.assertEqual(self.client.get('/api/base-conhecimento/busca',params={'q':'clareamento'}).status_code,503)

if __name__ == '__main__': unittest.main()
