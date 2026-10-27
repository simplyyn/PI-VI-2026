import json
import os
import unittest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock, patch
from llm import GeminiClient, GroqClient, create_llm, configured_model, LLMUnavailable

class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return json.dumps(self.data).encode()

class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'SMARTDENT_LLM_ENABLED':'true','SMARTDENT_LLM_PROVIDER':'gemini','GEMINI_API_KEY':'google-test-placeholder','GEMINI_MODEL':'gemini-test'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_provider_selection_and_request(self):
        self.assertIsInstance(create_llm(),GeminiClient)
        self.assertEqual(configured_model(),'gemini-test')
        with patch.dict(os.environ,{'SMARTDENT_LLM_PROVIDER':'groq'}): self.assertIsInstance(create_llm(),GroqClient)
        with patch.dict(os.environ,{'SMARTDENT_LLM_PROVIDER':'inexistente'}):
            with self.assertRaises(LLMUnavailable): create_llm()
        def opener(request,timeout):
            self.assertEqual(timeout,20)
            self.assertNotIn('google-test-placeholder',request.full_url)
            self.assertEqual(request.get_header('X-goog-api-key'),'google-test-placeholder')
            body=json.loads(request.data)
            self.assertEqual(body['systemInstruction']['parts'][0]['text'],'Regra de teste')
            self.assertEqual(body['contents'][0]['role'],'model')
            self.assertEqual(body['contents'][1]['parts'][0]['text'],'Pergunta fictícia')
            return Response({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'raciocínio oculto','thought':True},{'text':'Resposta de teste'}]}}]})
        answer=GeminiClient(opener).generate([{'role':'system','content':'Regra de teste'},{'role':'assistant','content':'Anterior'},{'role':'user','content':'Pergunta fictícia'}])
        self.assertEqual(answer,'Resposta de teste')

    def test_disabled_missing_and_wrong_key_do_not_send(self):
        opener=Mock()
        for updates in [{'SMARTDENT_LLM_ENABLED':'false'},{'GEMINI_API_KEY':''},{'GEMINI_API_KEY':'grok_placeholder'}]:
            with patch.dict(os.environ,updates):
                with self.assertRaises(LLMUnavailable): GeminiClient(opener).generate([])
        opener.assert_not_called()

    def test_http_timeout_and_invalid_responses(self):
        for code in (400,401,403,404,429,503):
            opener=Mock(side_effect=HTTPError('https://example.test',code,'erro',{},BytesIO(b'private-provider-error')))
            with self.assertRaises(LLMUnavailable) as result: GeminiClient(opener).generate([])
            self.assertNotIn('private-provider-error',str(result.exception))
            self.assertNotIn('google-test-placeholder',str(result.exception))
        with self.assertRaisesRegex(LLMUnavailable,'20 segundos'):
            GeminiClient(Mock(side_effect=TimeoutError())).generate([])
        for data in [{},{'candidates':[]},{'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'incompleto'}]}}]},
                     {'candidates':[{'content':{'parts':[{'text':''}]}}]}, {'promptFeedback':{'blockReason':'SAFETY'}}]:
            with self.assertRaises(LLMUnavailable): GeminiClient(lambda *a,**k:Response(data)).generate([])

if __name__=='__main__': unittest.main()
