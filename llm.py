"""Clientes REST Groq/Gemini, sem SDK. Não chamam serviços com LLM desativado."""
import json
import os
import socket
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

class LLMUnavailable(RuntimeError):
    pass


def configured_model():
    if os.getenv('SMARTDENT_LLM_PROVIDER','groq').strip().lower() == 'gemini':
        return os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
    return os.getenv('GROQ_MODEL','')


def create_llm():
    provider=os.getenv('SMARTDENT_LLM_PROVIDER','groq').strip().lower()
    if provider == 'gemini':
        return GeminiClient()
    if provider == 'groq':
        return GroqClient()
    raise LLMUnavailable('Provedor inválido. Configure SMARTDENT_LLM_PROVIDER=gemini ou groq.')


class GeminiClient:
    def __init__(self, opener=urlopen):
        self.opener=opener

    def generate(self,messages):
        if os.getenv('SMARTDENT_LLM_ENABLED','false').lower() != 'true':
            raise LLMUnavailable('LLM desativado. Configure SMARTDENT_LLM_ENABLED=true para usar Gemini.')
        key=(os.getenv('GEMINI_API_KEY') or '').strip()
        model=(os.getenv('GEMINI_MODEL') or 'gemini-3.5-flash-lite').strip()
        if not key:
            raise LLMUnavailable('Gemini não configurado. Preencha GEMINI_API_KEY no .env com uma chave do Google AI Studio.')
        if key.startswith(('grok_','xai-','gsk_')):
            raise LLMUnavailable('A chave não corresponde ao Gemini. Gere uma chave no Google AI Studio.')
        contents=[]
        instructions=[]
        for message in messages:
            if message['role']=='system': instructions.append(message['content'])
            else: contents.append({'role':'model' if message['role']=='assistant' else 'user','parts':[{'text':message['content']}]})
        body={'contents':contents,'generationConfig':{'temperature':0,'maxOutputTokens':2048}}
        if instructions: body['systemInstruction']={'parts':[{'text':'\n'.join(instructions)}]}
        request=Request('https://generativelanguage.googleapis.com/v1beta/models/'+quote(model,safe='')+':generateContent',
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
        try:
            with self.opener(request,timeout=20) as response:
                raw=response.read(1048577)
            if len(raw)>1048576: raise ValueError('Resposta excessiva')
            data=json.loads(raw)
            candidate=data['candidates'][0]
            if candidate.get('finishReason') not in (None,'STOP'):
                raise ValueError('Resposta incompleta ou bloqueada')
            text=''.join(part['text'] for part in candidate['content']['parts'] if isinstance(part.get('text'),str) and not part.get('thought',False))
            if not text.strip(): raise ValueError('Resposta vazia')
            return text.strip()
        except HTTPError as exc:
            code=exc.code
            exc.close()
            errors={400:'Gemini rejeitou a solicitação. Confira a chave, o modelo e os limites de contexto.',
                    401:'Gemini recusou a chave. Gere uma chave válida no Google AI Studio.',
                    403:'Gemini negou o acesso. Confira a chave, as permissões e a disponibilidade na sua conta/região.',
                    404:'Modelo Gemini indisponível. Confira GEMINI_MODEL e os modelos disponíveis na sua conta.',
                    429:'Limite de uso do Gemini atingido ou cota indisponível. Confira a cota gratuita no Google AI Studio e tente mais tarde.'}
            raise LLMUnavailable(errors.get(code,f'Gemini indisponível (HTTP {code}). Tente novamente mais tarde.')) from None
        except (socket.timeout,TimeoutError):
            raise LLMUnavailable('Gemini não respondeu em até 20 segundos. Tente novamente.') from None
        except (URLError,OSError):
            raise LLMUnavailable('Não foi possível conectar ao Gemini. Confira sua conexão de internet.') from None
        except (ValueError,KeyError,IndexError,TypeError,AttributeError):
            raise LLMUnavailable('Gemini retornou uma resposta vazia, incompleta ou bloqueada. Tente novamente.') from None

class GroqClient:
    def __init__(self, opener=urlopen):
        self.opener = opener

    def generate(self, messages):
        if os.getenv('SMARTDENT_LLM_ENABLED','false').lower() != 'true':
            raise LLMUnavailable('LLM desativado; requer autorização para chamadas reais')
        key, model = os.getenv('GROQ_API_KEY'), os.getenv('GROQ_MODEL')
        if not key or not model:
            raise LLMUnavailable('Provedor não configurado')
        key=key.strip()
        if key.startswith(('grok_','xai-')):
            raise LLMUnavailable('A chave configurada não corresponde ao Groq. Gere uma chave em console.groq.com/keys e atualize GROQ_API_KEY no .env.')
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
        except HTTPError as exc:
            code=exc.code
            exc.close()
            errors={
                400:'Groq rejeitou a solicitação. Confira o modelo configurado e os limites de contexto.',
                401:'Groq recusou a chave de API. Confira se ela é válida e não foi revogada.',
                403:'Groq negou o acesso. Confira as permissões da chave e da conta.',
                404:'Modelo ou recurso não encontrado no Groq. Confira GROQ_MODEL.',
                429:'Limite de uso do Groq atingido. Aguarde e tente novamente; consulte os limites da conta.',
            }
            raise LLMUnavailable(errors.get(code,f'Groq indisponível (HTTP {code}). Tente novamente mais tarde.')) from None
        except (socket.timeout, TimeoutError):
            raise LLMUnavailable('Groq não respondeu em até 20 segundos. Tente novamente.') from None
        except (URLError,OSError):
            raise LLMUnavailable('Não foi possível conectar ao Groq. Confira a conexão de internet.') from None
        except (ValueError,KeyError,IndexError,TypeError):
            raise LLMUnavailable('Groq retornou uma resposta inválida ou vazia. Tente novamente.') from None
