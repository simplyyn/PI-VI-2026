import json
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from llm import GeminiClient, GroqClient, LLMUnavailable
from usage import totals


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return json.dumps(self.data).encode()


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file=self.tmp.name+'/usage.jsonl'
        env=patch.dict(os.environ,{'SMARTDENT_USAGE_PATH':self.file,'SMARTDENT_LLM_ENABLED':'true','GEMINI_API_KEY':'test-placeholder','GEMINI_MODEL':'test','GROQ_API_KEY':'test-placeholder','GROQ_MODEL':'test'})
        env.start();self.addCleanup(env.stop)

    def payload(self):
        return dict(candidates=[{'content':{'parts':[{'text':'Resposta fictícia'}]}}],usageMetadata={'promptTokenCount':12,'candidatesTokenCount':7,'totalTokenCount':19})

    def test_retry_after_and_provider_counts_without_sensitive_content(self):
        error=HTTPError('https://example.test',429,'private',{'Retry-After':'0'},BytesIO(b'private-error'))
        opener=Mock(side_effect=[error,Response(self.payload())]);sleep=Mock()
        result=GeminiClient(opener,clinic='a',sleeper=sleep).generate([{'role':'user','content':'private-patient'}])
        self.assertEqual(result,'Resposta fictícia')
        self.assertEqual(opener.call_count,2);sleep.assert_called_once_with(0)
        usage=totals('a')
        self.assertEqual((usage['tokens_entrada'],usage['tokens_saida']),(12,7))
        self.assertEqual(totals('b')['chamadas_registradas'],0)
        with open(self.file,encoding='utf-8') as stream: raw=stream.read()
        self.assertNotIn('private',raw);self.assertNotIn('placeholder',raw);self.assertNotIn('Resposta',raw)

    def test_long_retry_delay_and_permanent_errors_do_not_retry(self):
        for code,headers in [(429,{'Retry-After':'120'}),(401,{}),(403,{})]:
            opener=Mock(side_effect=HTTPError('https://example.test',code,'private',headers,BytesIO()))
            sleep=Mock()
            with self.assertRaises(LLMUnavailable): GeminiClient(opener,sleeper=sleep).generate([])
            self.assertEqual(opener.call_count,1);sleep.assert_not_called()

    def test_transient_retry_is_bounded_and_missing_metadata_is_not_zero_usage(self):
        opener=Mock(side_effect=HTTPError('https://example.test',503,'private',{},BytesIO()))
        with self.assertRaises(LLMUnavailable): GeminiClient(opener,sleeper=Mock()).generate([])
        self.assertEqual(opener.call_count,2)
        payload=self.payload();payload.pop('usageMetadata')
        GeminiClient(lambda *a,**k:Response(payload),clinic='a').generate([])
        self.assertEqual(totals('a')['chamadas_sem_contagem'],1)

    def test_groq_counts_and_network_timeout_no_silent_answer(self):
        payload={'choices':[{'message':{'content':'Teste'}}],'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7}}
        GroqClient(lambda *a,**k:Response(payload),clinic='a').generate([])
        self.assertEqual(totals('a')['tokens_entrada'],3)
        with self.assertRaises(LLMUnavailable): GeminiClient(Mock(side_effect=TimeoutError())).generate([])
