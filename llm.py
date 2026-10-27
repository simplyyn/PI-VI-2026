"""Cliente Groq sem SDK. Nenhuma chamada ocorre com SMARTDENT_LLM_ENABLED=false."""
import json
import os
import socket
from urllib.request import Request, urlopen
from urllib.error import URLError

class LLMUnavailable(RuntimeError):
    pass

class GroqClient:
    def __init__(self, opener=urlopen):
        self.opener = opener

    def generate(self, messages):
        if os.getenv('SMARTDENT_LLM_ENABLED','false').lower() != 'true':
            raise LLMUnavailable('LLM desativado; requer autorização para chamadas reais')
        key, model = os.getenv('GROQ_API_KEY'), os.getenv('GROQ_MODEL')
        if not key or not model:
            raise LLMUnavailable('Provedor não configurado')
        request = Request('https://api.groq.com/openai/v1/chat/completions',
            data=json.dumps({'model':model,'messages':messages,'temperature':0,'max_tokens':700}).encode(),
            # User-Agent próprio: o Cloudflare do Groq bloqueia o padrão "Python-urllib" (403, erro 1010).
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'smartdent/1.0'},method='POST')
        try:
            with self.opener(request, timeout=20) as response:
                raw = response.read(1048577)
            if len(raw)>1048576:
                raise ValueError('Resposta excessiva')
            text = json.loads(raw)['choices'][0]['message']['content']
            if not isinstance(text,str) or not text.strip():
                raise ValueError('Resposta vazia')
            return text.strip()
        except (URLError, socket.timeout, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
            raise LLMUnavailable('Provedor indisponível ou resposta inválida') from None
