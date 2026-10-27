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

    def test_retrieval_handles_simple_questions_and_rephrasing(self):
        from seed_demo import seed
        seed(self.repo,'a')
        retriever=LocalKeywordRetriever(self.repo)
        for question in ['Boa tarde! Quais os horários de funcionamento e a política para remarcar uma consulta?',
                         'Quando abre e como faço para reagendar?',
                         'Qual o expediente e a regra de remarcação?']:
            documents=retriever.retrieve('a',question)
            titles={d['titulo'] for d in documents}
            self.assertIn('Horários de funcionamento e agendamento',titles)
            self.assertIn('Políticas, convênios e pagamento',titles)
        self.assertEqual(retriever.retrieve('a','Bom dia!'),[])
        self.assertEqual(retriever.retrieve('b','Como remarcar?'),[])
        self.assertIn('Políticas, convênios e pagamento',{d['titulo'] for d in retriever.retrieve('a','Tem Pix?')})

    def test_conversation_examples_preserve_history_and_show_complaint(self):
        from seed_demo import seed
        from populate_conversations import populate,EXAMPLE_COMPLAINT
        seed(self.repo,'a')
        attendance=self.repo.list('attendance','a')[0]
        self.repo.append_message('a',attendance['id'],dict(autor='human',texto='Histórico preservado',criado_em='2026-10-27T10:00:00+00:00'))
        populate(self.repo,'a')
        conversations=self.repo.list('attendance','a')
        self.assertTrue(all(any(m['autor']=='client' for m in a['mensagens']) for a in conversations))
        self.assertTrue(any(m['texto']=='Histórico preservado' for m in conversations[0]['mensagens']))
        bruno=next(a for a in conversations if a['cliente']=='Bruno Demonstração')
        self.assertTrue(any(m['texto']==EXAMPLE_COMPLAINT for m in bruno['mensagens']))
        classification=self.repo.list('complaints','a')[0]
        self.assertEqual((classification['categoria'],classification['origem']),('tempo_espera','manual'))
        self.assertEqual(populate(self.repo,'a'),dict(mensagens_adicionadas=0,reclamacoes_classificadas=0))
        self.assertEqual(self.repo.list('attendance','b'),[])

    def test_initial_guidance_is_safe_and_does_not_call_model(self):
        from guidance import initial_guidance
        from unittest.mock import Mock
        retriever,model=Mock(),Mock()
        result=AttendanceAgent(retriever,model).answer('a','Meu dente está doendo')
        self.assertEqual(result['tipo'],'orientacao_inicial')
        self.assertEqual(result['procedimento_sugerido'],'Consulta de avaliação odontológica')
        self.assertFalse(result['gerado_por_llm'])
        retriever.retrieve.assert_not_called()
        model.generate.assert_not_called()
        urgent=initial_guidance('Estou com inchaço na boca e dificuldade para respirar')
        self.assertEqual(urgent['tipo'],'orientacao_urgente')
        self.assertIsNone(urgent['procedimento_sugerido'])
        self.assertIsNone(initial_guidance('Não sinto dor no dente. Qual o preço da avaliação?'))
        self.assertIsNone(initial_guidance('Quais os horários de funcionamento?'))

    def test_expanded_catalog_and_schedule_are_idempotent(self):
        from seed_demo import seed
        from enhance_clinic import enhance
        from catalog import PROCEDURE_OPTIONS
        from datetime import date
        seed(self.repo,'a')
        result=enhance(self.repo,'a',today=date(2026,10,27))
        self.assertEqual(result,dict(agendamentos_criados=4,artigos_criados=1))
        self.assertEqual(len(PROCEDURE_OPTIONS),10)
        self.assertEqual(enhance(self.repo,'a',today=date(2026,10,27)),dict(agendamentos_criados=0,artigos_criados=0))
        self.assertEqual(self.repo.list('appointments','b'),[])
        for appointment in self.repo.list('appointments','a'):
            self.assertGreater(appointment['data'],'2026-10-27')
            self.assertLess(date.fromisoformat(appointment['data']).weekday(),5)

    def test_demo_seed_idempotence_scope_and_context(self):
        from seed_demo import seed
        result=seed(self.repo,'a')
        self.assertEqual(result,{'pacientes':4,'estoque':5,'artigos':3})
        self.assertEqual(seed(self.repo,'a'),{'pacientes':0,'estoque':0,'artigos':0})
        self.assertEqual(self.repo.list('kb','b'),[])
        self.assertEqual(len(SQLiteRepository(self.path).list('patients','a')),4)
        retriever=LocalKeywordRetriever(self.repo)
        for question in ['precos dos procedimentos','horarios de funcionamento','politicas de cancelamento']:
            documents=retriever.retrieve('a',question)
            self.assertTrue(documents)
            self.assertTrue(all('FICTÍCIOS' in d['conteudo'] for d in documents))

    def test_prepare_existing_conversations_names_and_simulated_quote(self):
        from seed_demo import seed
        from prepare_clinic import prepare
        seed(self.repo,'a')
        result=prepare(self.repo,'a')
        self.assertEqual(result['pacientes_vinculados'],4)
        self.assertIsNotNone(result['orcamento_atendimento_id'])
        count=len(self.repo.list('attendance','a'))
        prepare(self.repo,'a')
        self.assertEqual(len(self.repo.list('attendance','a')),count)
        quote=next(a for a in self.repo.list('attendance','a') if a['id']==result['orcamento_atendimento_id'])
        self.assertEqual(len(quote['mensagens']),2)
        self.assertIn('R$ 300,00',quote['mensagens'][1]['texto'])
        self.assertEqual(self.repo.list('attendance','b'),[])

    def test_llm_provider_mismatch_and_sanitized_http_errors(self):
        from urllib.error import HTTPError
        from io import BytesIO
        from unittest.mock import Mock
        opener=Mock()
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true','GROQ_API_KEY':'grok_placeholder','GROQ_MODEL':'test-model'}):
            with self.assertRaisesRegex(LLMUnavailable,'não corresponde ao Groq'):
                GroqClient(opener).generate([])
            opener.assert_not_called()
        with patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true','GROQ_API_KEY':'test-placeholder','GROQ_MODEL':'test-model'}):
            for code in (400,401,403,404,429,503):
                opener.side_effect=HTTPError('https://example.test',code,'erro',{},BytesIO(b'private-body-placeholder'))
                with self.assertRaises(LLMUnavailable) as error:
                    GroqClient(opener).generate([])
                self.assertNotIn('private-body-placeholder',str(error.exception))
                self.assertNotIn('test-placeholder',str(error.exception))

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
