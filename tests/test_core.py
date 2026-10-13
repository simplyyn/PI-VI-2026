import json
import os
import tempfile
import unittest
from unittest.mock import patch
from auth import hash_password, verify_password, autenticar
from persistence import SQLiteRepository
from llm import GroqClient, LLMUnavailable
from rag import AttendanceAgent, LocalKeywordRetriever, PendingSemanticRetriever, RetrievalUnavailable

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

if __name__ == '__main__': unittest.main()
