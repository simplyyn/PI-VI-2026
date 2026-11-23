"""Conversation ownership, pending replies, batch drafts and atomic delivery."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from services import ClinicRecords


class WorkflowConflict(ValueError):
    pass


def require_workflows(repo):
    if not getattr(repo,'supports_workflows',False):
        raise WorkflowConflict('O repositório configurado não suporta operações integradas.')


def now(): return datetime.now(timezone.utc).isoformat()


def version(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,default=str).encode()).hexdigest()


def record(repo,kind,clinic,identifier):
    row=next((r for r in repo.list(kind,clinic) if r['id']==identifier),None)
    if row is None: raise LookupError('Registro não encontrado')
    return row


def audit(repo,user,action,target,fields=()):
    repo.save('audit',user['empresa_id'],dict(user_id=user['id'],action=action,target=target,fields=list(fields),created_at=now()))


def waiting_messages(attendance):
    """Order is append order; a draft or an automatic handoff is never a reply."""
    messages=attendance.get('mensagens',[])
    boundary=-1
    for index,m in enumerate(messages):
        valid=m.get('responde',True) and m.get('autor') in ('human','ai')
        if attendance['status']=='escalated' and m.get('autor')=='ai': valid=False
        if valid: boundary=index
    return [m for m in messages[boundary+1:] if m.get('autor')=='client']


def pending(repo,clinic):
    rows=[]
    for item in ClinicRecords(repo,clinic).list('attendance'):
        messages=waiting_messages(item)
        if messages:
            rows.append(dict(id=item['id'],cliente=item['cliente'],mensagens_pendentes=len(messages),
                             desde=messages[0]['criado_em'],ultima_mensagem=messages[-1]['texto'],
                             status=item['status'],versao=version(item)))
    rows.sort(key=lambda r:(r['desde'],r['id']))
    links={l['attendance_id']:l['patient_id'] for l in repo.list('patient_links',clinic)} if getattr(repo,'supports_workflows',False) else {}
    patients={links[r['id']] for r in rows if r['id'] in links}
    return dict(conversas=len(rows),pacientes_identificados=len(patients),conversas_sem_vinculo=sum(r['id'] not in links for r in rows),mensagens=sum(r['mensagens_pendentes'] for r in rows),itens=rows,
                criterio='Mensagens do paciente após a última resposta enviada. Em escalados, somente resposta humana encerra a espera.')


def customer_patient(repo,user):
    require_workflows(repo)
    links=[r for r in repo.list('customer_links',user['empresa_id']) if r['user_id']==user['id']]
    if len(links)!=1: raise WorkflowConflict('Seu acesso precisa ser vinculado a um paciente pela clínica. Contate a recepção.')
    return ClinicRecords(repo,user['empresa_id']).get('patients',links[0]['patient_id'])


def customer_conversation(repo,user):
    patient=customer_patient(repo,user)
    return ClinicRecords(repo,user['empresa_id']).patient_attendance(patient['id'])


def evaluations_for(repo, user):
    return [rating for rating in repo.list('answer_ratings', user['empresa_id'])
            if rating['user_id'] == user['id']]


def rate_answer(repo, user, attendance_id, message_id, useful):
    clinic = user['empresa_id']
    with repo.transaction() as tx:
        item = customer_conversation(tx, user) if user['role'] == 'customer' else record(tx, 'attendance', clinic, attendance_id)
        if item['id'] != attendance_id or not any(
            message.get('id') == message_id and message['autor'] == 'ai' and message.get('gerado_por_llm')
            for message in item['mensagens']
        ):
            raise LookupError('Resposta não encontrada')
        existing = next((rating for rating in evaluations_for(tx, user)
                         if (rating['attendance_id'], rating['message_id']) == (attendance_id, message_id)), None)
        if existing and existing['util'] == useful:
            return {'message_id': message_id, 'util': useful}
        rating = tx.save('answer_ratings', clinic, dict(attendance_id=attendance_id, message_id=message_id,
                         user_id=user['id'], role=user['role'], util=useful, criado_em=now()),
                         existing['id'] if existing else None)
        return {'message_id': rating['message_id'], 'util': rating['util']}


def deliver(repo,user,attendance_id,text,key,expected=None,autor='human',responde=True):
    """Compare-and-append with durable idempotency and audit in the same transaction."""
    require_workflows(repo)
    if not text.strip() or len(text)>4000: raise ValueError('Mensagem deve ter de 1 a 4000 caracteres')
    scoped=f"{user['id']}:{key}"
    with repo.transaction() as tx:
        receipts=[r for r in tx.list('delivery_receipts',user['empresa_id']) if r['key']==scoped]
        if receipts:
            if receipts[0]['text_hash']!=version(text) or receipts[0]['attendance_id']!=attendance_id: raise WorkflowConflict('A chave de envio já foi usada com outra mensagem.')
            return dict(record(tx,'attendance',user['empresa_id'],attendance_id),envio_repetido=True)
        item=record(tx,'attendance',user['empresa_id'],attendance_id)
        if expected and version(item)!=expected: raise WorkflowConflict('A conversa mudou. Revise as mensagens antes de enviar.')
        message=dict(id=uuid4().hex,texto=text.strip(),autor=autor,criado_em=now(),responde=responde)
        result=tx.append_message(user['empresa_id'],attendance_id,message)
        tx.save('delivery_receipts',user['empresa_id'],dict(key=scoped,text_hash=version(text),attendance_id=attendance_id))
        audit(tx,user,'message_sent',attendance_id,('texto',))
        return result


class CustomerChat:
    def __init__(self,repo,user):
        if user.get('role')!='customer':raise WorkflowConflict('Este canal é exclusivo do paciente autenticado.')
        self.repo,self.user=repo,user

    def get(self):
        item=customer_conversation(self.repo,self.user)
        appointments=[a for a in ClinicRecords(self.repo,self.user['empresa_id']).list('appointments')
                      if a['paciente_id']==customer_patient(self.repo,self.user)['id']]
        messages=item.get('mensagens',[])
        action = next((message['acao'] for message in reversed(messages) if message.get('acao')), None)
        ratings = {r['message_id']: r['util'] for r in evaluations_for(self.repo, self.user) if r['attendance_id'] == item['id']}
        return dict(atendimento_id=item['id'],mensagens=messages,status=item['status'],agendamentos=appointments,acao=action,avaliacoes=ratings)

    def send(self,text,key,agent,automatic=True):
        require_workflows(self.repo)
        with self.repo.transaction() as tx:
            item=customer_conversation(tx,self.user)
            receipts=[r for r in tx.list('chat_requests',self.user['empresa_id']) if r['user_id']==self.user['id'] and r['key']==key]
            if receipts:
                receipt=receipts[0]
                if receipt['text_hash']!=version(text): raise WorkflowConflict('Chave de mensagem já utilizada com outro texto.')
                return dict(CustomerChat(tx,self.user).get(),aviso=receipt.get('aviso','Mensagem já registrada; não será duplicada.'))
            item=tx.append_message(self.user['empresa_id'],item['id'],dict(id=uuid4().hex,autor='client',texto=text,criado_em=now()))
            if item['status']=='resolved':
                data=dict(item,status='pending');identifier=data.pop('id')
                item=tx.save('attendance',self.user['empresa_id'],data,identifier)
            request=tx.save('chat_requests',self.user['empresa_id'],dict(user_id=self.user['id'],key=key,text_hash=version(text),state='processing',created_at=now()))
            captured=version(item)
        from assistant import normalize
        human=not automatic or any(term in normalize(text) for term in ('falar com atendente','falar com humano','atendimento humano','falar com a recepcao','falar com recepcao','falar com a equipe','falar com uma pessoa')) or item['status']=='escalated'
        answer=None;warning=''
        try:
            if human:
                answer=dict(resposta='Sua mensagem foi encaminhada à equipe. Aguarde o atendimento humano.',tipo='encaminhamento',gerado_por_llm=False)
            else: answer=agent(text,item)
        except Exception as error:
            from llm import LLMUnavailable
            from rag import RetrievalUnavailable
            if not isinstance(error,(LLMUnavailable,RetrievalUnavailable,WorkflowConflict)): raise
            warning='Sua mensagem foi salva. A resposta automática está indisponível; a equipe pode responder pelo atendimento.'
        with self.repo.transaction() as tx:
            current=record(tx,'attendance',self.user['empresa_id'],item['id'])
            if version(current)!=captured:
                warning='Sua mensagem foi salva. A conversa mudou durante a geração; a equipe verificará as mensagens.'
            elif answer:
                escalated=human or answer.get('tipo')=='orientacao_urgente'
                substantive=not escalated and answer.get('tipo')!='sem_contexto'
                action={k:answer[k] for k in ('estado','agendamento_id','opcoes') if k in answer} or None
                tx.append_message(self.user['empresa_id'],item['id'],dict(id=uuid4().hex,autor='ai',texto=answer['resposta'],
                    criado_em=now(),responde=substantive,gerado_por_llm=answer.get('gerado_por_llm',False),acao=action))
                if escalated:
                    current=record(tx,'attendance',self.user['empresa_id'],item['id'])
                    current.pop('id',None);current.update(status='escalated',canal='human')
                    tx.save('attendance',self.user['empresa_id'],current,item['id'])
            request.update(state='done',aviso=warning)
            identifier=request.pop('id')
            tx.save('chat_requests',self.user['empresa_id'],request,identifier)
        return dict(self.get(),aviso=warning)


class BatchReplies:
    def __init__(self,repo,user):
        require_workflows(repo)
        if user.get('role')!='owner':raise WorkflowConflict('Somente o responsável pode preparar respostas em lote.')
        self.repo,self.user,self.clinic=repo,user,user['empresa_id']

    def prepare(self,generate,limit=5):
        selected=pending(self.repo,self.clinic)['itens'][:limit]
        fingerprint=version(selected)
        with self.repo.transaction() as tx:
            for existing in reversed(tx.list('reply_batches',self.clinic)):
                recent=datetime.now(timezone.utc)-datetime.fromisoformat(existing['created_at'])<timedelta(minutes=5)
                if existing['user_id']==self.user['id'] and recent:
                    if existing.get('state')=='generating':raise WorkflowConflict('Já existe um lote sendo preparado. Aguarde antes de gerar novamente.')
                    if existing.get('fingerprint')==fingerprint:return existing
            draft=tx.save('reply_batches',self.clinic,dict(user_id=self.user['id'],created_at=now(),items=[],state='generating',fingerprint=fingerprint))
        items=[]
        for row in selected:
            item=record(self.repo,'attendance',self.clinic,row['id'])
            try:
                answer=generate(row['ultima_mensagem'],item)
                suggestion=answer['resposta'];error=''
                if answer.get('tipo')=='sem_contexto': error='Sem contexto suficiente. Revise e escreva uma resposta manual.'
            except Exception as exc:
                from llm import LLMUnavailable
                from rag import RetrievalUnavailable
                if not isinstance(exc,(LLMUnavailable,RetrievalUnavailable)): raise
                suggestion='';error=str(exc)
            items.append(dict(**row,texto=suggestion,erro=error))
        draft.update(items=items,state='ready')
        identifier=draft.pop('id')
        draft=self.repo.save('reply_batches',self.clinic,draft,identifier)
        return draft

    def get(self,identifier):
        item=record(self.repo,'reply_batches',self.clinic,identifier)
        if item['user_id']!=self.user['id']: raise LookupError('Lote não encontrado')
        if datetime.now(timezone.utc)-datetime.fromisoformat(item['created_at'])>timedelta(minutes=30):
            raise WorkflowConflict('Lote expirado. Gere uma nova prévia.')
        return item

    def send(self,identifier,items):
        batch=self.get(identifier)
        if batch.get('state')!='ready':raise WorkflowConflict('A prévia ainda não terminou.')
        if len({i['id'] for i in items})!=len(items):raise WorkflowConflict('Há atendimentos repetidos no lote.')
        known={r['id']:r for r in batch['items']}
        results=[]
        for item in items:
            aid=item['id']
            if aid not in known: raise ValueError('Atendimento fora do lote')
            try:
                delivered=deliver(self.repo,self.user,aid,item['texto'],f'batch:{identifier}:{aid}',expected=known[aid]['versao'])
                results.append(dict(id=aid,status='ja_enviado' if delivered.get('envio_repetido') else 'enviado'))
            except (WorkflowConflict,LookupError,ValueError) as exc:
                results.append(dict(id=aid,status='revisar',erro=str(exc)))
        return dict(resultados=results,enviados=sum(r['status']=='enviado' for r in results))
