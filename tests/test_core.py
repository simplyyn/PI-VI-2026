import json
import os
import tempfile
import unittest
from unittest.mock import patch
from auth import hash_password, verify_password, autenticar
from persistence import SQLiteRepository
from llm import GroqClient, LLMUnavailable
from rag import AttendanceAgent, LocalKeywordRetriever, PendingSemanticRetriever, PgVectorRetriever, RetrievalUnavailable, create_retriever
from embeddings import EmbeddingUnavailable, chunk_text
from analysis import ComplaintClassifier, parse_verdict

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name+'/test.sqlite3'
        self.repo = SQLiteRepository(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hash_login_and_persistence(self):
        password = 'senha-ficticia-testes'
        encoded = hash_password(password)
        self.assertNotEqual(encoded,hash_password(password))
        self.assertTrue(verify_password(password,encoded))
        self.assertFalse(verify_password('incorreta',encoded))
        self.assertFalse(verify_password(password,'malformado'))
        self.repo.add_user(dict(email='owner@example.test',password_hash=encoded,role='owner',empresa_id='a'))
        reopened = SQLiteRepository(self.path)
        self.assertIsNotNone(autenticar('OWNER@example.test',password,reopened))
        self.assertIsNone(autenticar('owner@example.test','errada',reopened))
        self.assertIsNone(autenticar('ausente@example.test',password,reopened))

    def test_tenant_crud_and_stock(self):
        item = self.repo.save('stock','a',{'quantidade':2,'minimo':1})
        self.assertEqual(self.repo.list('stock','b'),[])
        with self.assertRaises(LookupError): self.repo.move('b',item['id'],1)
        with self.assertRaises(LookupError): self.repo.save('stock','b',{},item['id'])
        with self.assertRaises(LookupError): self.repo.delete('stock','b',item['id'])
        with self.assertRaises(ValueError): self.repo.move('a',item['id'],-3)
        self.assertEqual(self.repo.list('stock','a')[0]['quantidade'],2)
        self.assertEqual(self.repo.move('a',item['id'],3)['quantidade'],5)
        self.assertEqual(SQLiteRepository(self.path).list('stock','a')[0]['quantidade'],5)
        self.repo.delete('stock','a',item['id'])
        self.assertEqual(self.repo.list('stock','a'),[])

    def test_real_lexical_retrieval_and_agent(self):
        self.repo.save('kb','a',dict(titulo='Documento fictício',conteudo='protocolo fictício alfa',status=True))
        self.repo.save('kb','b',dict(titulo='Outra clínica',conteudo='protocolo secreto beta',status=True))
        self.assertEqual(SQLiteRepository(self.path).list('kb','a')[0]['conteudo'],'protocolo fictício alfa')
        class FakeModel:
            def generate(self,messages):
                self.messages = messages
                return 'Resposta simulada [1]'
        model = FakeModel()
        agent = AttendanceAgent(LocalKeywordRetriever(self.repo),model)
        self.assertTrue(agent.answer('a','protocolo alfa')['gerado_por_llm'])
        self.assertNotIn('beta',str(model.messages))
        result = agent.answer('a','informação inexistente')
        self.assertFalse(result['gerado_por_llm'])
        with self.assertRaises(RetrievalUnavailable): PendingSemanticRetriever().retrieve('a','teste')

    def test_llm_disabled_timeout_invalid_and_success(self):
        def fail(*args,**kwargs): raise TimeoutError()
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'false'}):
            with self.assertRaises(LLMUnavailable): GroqClient(fail).generate([])
        class Response:
            def __init__(self,body): self.body=body
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return self.body
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true','GROQ_API_KEY':'test-placeholder','GROQ_MODEL':'test-model'}):
            with self.assertRaises(LLMUnavailable): GroqClient(fail).generate([])
            with self.assertRaises(LLMUnavailable): GroqClient(lambda *a,**k:Response(b'{}')).generate([])
            client = GroqClient(lambda *a,**k:Response(json.dumps({'choices':[{'message':{'content':'simulado'}}]}).encode()))
            self.assertEqual(client.generate([]),'simulado')

    def test_chunking_preserves_text_in_bounded_pieces(self):
        self.assertEqual(chunk_text('  curto\n texto '),['curto texto'])
        self.assertEqual(chunk_text('   '),[])
        text = ' '.join(f'Frase {i} sobre cuidados após o procedimento.' for i in range(60))+' '+'x'*1200
        chunks = chunk_text(text)
        self.assertGreater(len(chunks),3)
        self.assertTrue(all(len(c)<=600 for c in chunks))
        for i in (0,30,59):
            self.assertTrue(any(f'Frase {i} ' in c for c in chunks))

    def test_complaint_verdict_parsing(self):
        verdict = parse_verdict('Resultado:\n```json\n{"reclamacao": true, "categoria": "convenio", "motivo": "'+'m'*400+'"}\n```')
        self.assertEqual((verdict.reclamacao,verdict.categoria,len(verdict.motivo)),(True,'convenio',300))
        self.assertIsNone(parse_verdict('{"reclamacao": false, "categoria": "outros"}').categoria)
        for invalid in ['sem json','{"reclamacao": true}','{"reclamacao": true, "categoria": "inexistente"}','[1, 2]']:
            with self.assertRaises(LLMUnavailable): parse_verdict(invalid)
        class FakeModel:
            def generate(self,messages):
                self.messages = messages
                return '{"reclamacao": true, "categoria": "tempo_espera", "motivo": "Atraso"}'
        model = FakeModel()
        attendance = dict(cliente='Nome Sensível',preview='Esperei muito',mensagens=[dict(autor='human',texto='Lamentamos')])
        self.assertEqual(ComplaintClassifier(model).classify(attendance).categoria,'tempo_espera')
        self.assertNotIn('Nome Sensível',str(model.messages))
        self.assertIn('Lamentamos',str(model.messages))

    def test_retriever_selection(self):
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':''}):
            self.assertIsInstance(create_retriever(self.repo),PendingSemanticRetriever)
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':'local_keyword'}):
            self.assertIsInstance(create_retriever(self.repo),LocalKeywordRetriever)
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':'pgvector'}):
            with self.assertRaises(RetrievalUnavailable): create_retriever(self.repo).retrieve('a','teste')
        class SemanticRepository:
            supports_semantic_search = True
            def search_knowledge(self,clinic,question,limit): raise EmbeddingUnavailable('sem modelo')
        with patch.dict(os.environ,{'SMARTDENT_RETRIEVAL':''}):
            retriever = create_retriever(SemanticRepository())
            self.assertIsInstance(retriever,PgVectorRetriever)
            with self.assertRaises(RetrievalUnavailable): retriever.retrieve('a','teste')

if __name__ == '__main__': unittest.main()
