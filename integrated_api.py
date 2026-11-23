"""Authenticated endpoints for the integrated patient and owner workflows."""
from uuid import uuid4
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from security import require_user, csrf_check
from workflows import CustomerChat, BatchReplies, pending, record, deliver, require_workflows
from rag import AttendanceAgent,create_retriever
from guidance import initial_guidance
from patient_scope import booking_reply, patient_response

router=APIRouter()


def generation(request,user):
    from app import request_llm
    def answer(text,item):
        guidance = initial_guidance(text)
        if guidance and guidance['tipo'] == 'orientacao_urgente':
            return guidance
        active = user['role'] == 'customer' and bool(request.session.get('patient_booking'))
        local_reply = patient_response(text, booking_active=active)
        if local_reply is not None:
            return local_reply
        if user['role']=='customer':
            from professionals import PatientBooking
            if not active or booking_reply(text):
                booking=PatientBooking(request.app.state.repository,user,request.session).answer(text)
                if booking is not None:return booking
        history = [message for message in item.get('mensagens', [])
                   if message.get('autor') != 'client' or patient_response(message['texto']) is None]
        agent = AttendanceAgent(create_retriever(request.app.state.repository),request_llm(request))
        return agent.answer(user['empresa_id'], text, history, patient_facing=True)
    return answer


class CustomerMessage(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    texto: str=Field(min_length=1,max_length=2000)
    request_id: str=Field(min_length=8,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    resposta_automatica: bool=True


@router.get('/api/cliente/conversa')
def customer_conversation(request:Request):
    user=require_user(request,{'customer'})
    return customer_view(request, CustomerChat(request.app.state.repository,user).get())


@router.post('/api/cliente/retomar')
def resume_customer_ai(request:Request):
    from workflows import customer_conversation as own_conversation,audit
    user=require_user(request,{'customer'});csrf_check(request)
    repo=request.app.state.repository;require_workflows(repo)
    with repo.transaction() as tx:
        item=own_conversation(tx,user);identifier=item.pop('id')
        item.update(status='pending',canal='ai')
        tx.save('attendance',user['empresa_id'],item,identifier)
        audit(tx,user,'resume_automatic_assistant',identifier)
    return customer_view(request, CustomerChat(repo,user).get())


@router.post('/api/cliente/mensagens')
def customer_send(request:Request,data:CustomerMessage):
    user=require_user(request,{'customer'});csrf_check(request)
    generator=generation(request,user)
    result = CustomerChat(request.app.state.repository,user).send(data.texto,data.request_id,generator,data.resposta_automatica)
    return customer_view(request, result)


def customer_view(request, result):
    action = result.get('acao')
    if action and action.get('estado') not in {'concluido', 'cancelado'} and not request.session.get('patient_booking'):
        return dict(result, acao=None)
    return result


@router.get('/api/pendencias')
def pending_replies(request:Request):
    user=require_user(request,{'owner'})
    return pending(request.app.state.repository,user['empresa_id'])


@router.get('/api/profissionais')
def professional_list(request:Request,incluir_inativos:bool=False):
    user=require_user(request,{'owner','customer'});require_workflows(request.app.state.repository)
    return [p for p in request.app.state.repository.list('professionals',user['empresa_id']) if p['ativo'] or (incluir_inativos and user['role']=='owner')]


@router.get('/profissionais')
def professionals_page(request:Request):
    from auth import usuario_logado
    from fastapi.responses import RedirectResponse
    from app import templates
    user=usuario_logado(request)
    if not user or user['role']!='owner':return RedirectResponse('/login',status_code=302)
    require_workflows(request.app.state.repository)
    return templates.TemplateResponse('profissionais.html',dict(request=request,usuario=user,pagina='profissionais',profissionais=request.app.state.repository.list('professionals',user['empresa_id'])))


from professionals import Professional

@router.put('/api/profissionais/{identifier}')
def update_professional(identifier:int,request:Request,data:Professional):
    from professionals import update_profile
    user=require_user(request,{'owner'});csrf_check(request)
    return update_profile(request.app.state.repository,user,identifier,data)


@router.get('/api/precos')
def clinic_prices(request:Request):
    user=require_user(request,{'owner'});require_workflows(request.app.state.repository)
    return request.app.state.repository.list('prices',user['empresa_id'])


@router.get('/api/profissionais/{identifier}/horarios')
def professional_slots(identifier:int,request:Request,data:str,duracao:int=30):
    from datetime import date
    from professionals import available
    from fastapi import HTTPException
    user=require_user(request,{'owner','customer'});require_workflows(request.app.state.repository)
    if not 15<=duracao<=240:raise HTTPException(422,'Duração entre 15 e 240 minutos')
    date.fromisoformat(data)
    from workflows import customer_patient
    patient=customer_patient(request.app.state.repository,user)['id'] if user['role']=='customer' else -1
    return dict(horarios=available(request.app.state.repository,user['empresa_id'],identifier,data,duracao,patient))


@router.post('/api/respostas/lotes')
def prepare_batch(request:Request):
    user=require_user(request,{'owner'});csrf_check(request)
    return BatchReplies(request.app.state.repository,user).prepare(generation(request,user))


@router.get('/api/respostas/lotes/{identifier}')
def get_batch(identifier:int,request:Request):
    user=require_user(request,{'owner'})
    return BatchReplies(request.app.state.repository,user).get(identifier)


class ReplyItem(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    id: int=Field(gt=0)
    texto:str=Field(min_length=1,max_length=4000)


class BatchSend(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmado: Literal[True]
    items:list[ReplyItem]=Field(min_length=1,max_length=5)


@router.post('/api/respostas/lotes/{identifier}/enviar')
def send_batch(identifier:int,request:Request,data:BatchSend):
    user=require_user(request,{'owner'});csrf_check(request)
    return BatchReplies(request.app.state.repository,user).send(identifier,[i.model_dump() for i in data.items])


@router.get('/respostas')
def replies_page(request:Request):
    user=require_user(request,{'owner'})
    from app import templates
    return templates.TemplateResponse('batch_replies.html',dict(request=request,usuario=user,pagina='atendimentos'))
