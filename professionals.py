"""Structured professionals and availability. No diagnosis or choice of surgery."""
from datetime import datetime,timedelta,time,date
from pydantic import BaseModel,Field,ConfigDict,model_validator
from management import LOCAL_ZONE
from scheduling import AppointmentConflict,check_conflict,normalized
from uuid import uuid4


class Professional(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    nome:str=Field(min_length=1,max_length=100)
    especialidades:list[str]=Field(min_length=1,max_length=10)
    procedimentos:list[str]=Field(min_length=1,max_length=40)
    expediente:dict[str,list[list[str]]]
    duracao_padrao:int=Field(ge=15,le=240,default=30)
    ativo:bool=True

    @model_validator(mode='after')
    def valid_profile(self):
        for field in ('especialidades','procedimentos'):
            values=getattr(self,field)
            if any(not isinstance(v,str) or not v.strip() or len(v)>200 for v in values):
                raise ValueError('Informe nomes válidos de especialidades e procedimentos')
            setattr(self,field,list(dict.fromkeys(v.strip() for v in values)))
        for day,intervals in self.expediente.items():
            if day not in {str(i) for i in range(7)}:raise ValueError('Dia da semana inválido')
            previous=None
            for interval in intervals:
                if len(interval)!=2:raise ValueError('Informe início e fim de cada intervalo')
                try:a,b=(time.fromisoformat(v) for v in interval)
                except (ValueError,TypeError):raise ValueError('Horário inválido') from None
                if a>=b or a.second or b.second or a.tzinfo or b.tzinfo or (previous is not None and a<previous):
                    raise ValueError('Intervalos devem estar em ordem e não podem se sobrepor')
                previous=b
        return self


def update_profile(repo,user,identifier,profile):
    from workflows import record,require_workflows,audit,WorkflowConflict
    require_workflows(repo)
    with repo.transaction() as tx:
        old=record(tx,'professionals',user['empresa_id'],identifier)
        others=[p for p in tx.list('professionals',user['empresa_id']) if p['id']!=identifier]
        if any(normalized(p['nome'])==normalized(profile.nome) for p in others):
            raise WorkflowConflict('Já existe um profissional com esse nome na clínica.')
        changed=dict(profile.model_dump(),id=identifier)
        appointments=[a for a in tx.list('appointments',user['empresa_id']) if a.get('profissional_id')==identifier]
        today=datetime.now(LOCAL_ZONE).date().isoformat()
        for a in appointments:
            if a['status']!='cancelado' and a['data']>=today:
                if not profile.ativo:raise WorkflowConflict('Existem consultas futuras. Remarque ou cancele antes de inativar o profissional.')
                validate_professional([changed],dict(a,dentista=profile.nome))
        result=tx.save('professionals',user['empresa_id'],profile.model_dump(),identifier)
        if old['nome']!=profile.nome:tx.sync_professional_name(user['empresa_id'],identifier)
        audit(tx,user,'professional_update',identifier,[k for k in profile.model_dump() if old.get(k)!=getattr(profile,k)])
    return result


def validate_professional(professionals,data):
    if not professionals or data['status']=='cancelado': return data
    pid=data.get('profissional_id')
    matches=[p for p in professionals if p['id']==pid] if pid else [p for p in professionals if normalized(p['nome'])==normalized(data['dentista']).removeprefix('dr. ').removeprefix('dra. ')]
    if len(matches)!=1 or not matches[0]['ativo']: raise AppointmentConflict('Selecione um profissional ativo cadastrado: '+', '.join(p['nome'] for p in professionals if p['ativo']))
    p=matches[0]
    given=normalized(data['dentista']).removeprefix('dr. ').removeprefix('dra. ')
    if given!=normalized(p['nome']):raise AppointmentConflict('O nome e o identificador do profissional não correspondem. Selecione novamente.')
    if normalized(data['procedimento']) not in {normalized(s) for s in p['procedimentos']}:
        raise AppointmentConflict('Esse procedimento não está cadastrado para '+p['nome']+'. Escolha uma avaliação compatível.')
    day=date.fromisoformat(data['data']);start=time.fromisoformat(data['horario'])
    end=datetime.combine(day,start)+timedelta(minutes=data['duracao'])
    intervals=p['expediente'].get(str(day.weekday()),[])
    if end.date()!=day or not any(time.fromisoformat(a)<=start and end.time()<=time.fromisoformat(b) for a,b in intervals):
        raise AppointmentConflict('Horário fora do expediente de '+p['nome']+'. Consulte os horários disponíveis.')
    return dict(data,profissional_id=p['id'],dentista=p['nome'])


def available(repo,clinic,professional_id,day,duration=30,patient_id=-1):
    from workflows import record
    p=record(repo,'professionals',clinic,professional_id)
    if not p['ativo']: return []
    parsed=date.fromisoformat(day);values=[];now=datetime.now(LOCAL_ZONE)
    for a,b in p['expediente'].get(str(parsed.weekday()),[]):
        cursor=datetime.combine(parsed,time.fromisoformat(a),tzinfo=LOCAL_ZONE)
        end=datetime.combine(parsed,time.fromisoformat(b),tzinfo=LOCAL_ZONE)
        while cursor+timedelta(minutes=duration)<=end:
            data=dict(data=day,horario=cursor.strftime('%H:%M'),duracao=duration,dentista=p['nome'],paciente_id=patient_id,status='pendente')
            try: check_conflict(repo.list('appointments',clinic),data)
            except AppointmentConflict: pass
            else:
                if cursor>now: values.append(cursor.strftime('%H:%M'))
            cursor+=timedelta(minutes=30)
    return values


class PatientBooking:
    def __init__(self,repo,user,session): self.repo,self.user,self.session=repo,user,session

    def answer(self,text):
        import re
        from workflows import customer_patient,record
        from scheduling import SchedulingAgent
        m=normalized(text);state=self.session.get('patient_booking')
        intent=bool(re.search(r'\b(agend|marc|horarios|disponive)',m)) and any(w in m for w in ('consulta','limpeza','cirurg','avaliacao','horario','agend','marc'))
        if not state and not intent: return None
        if m in ('cancelar','desistir'):
            self.session.pop('patient_booking',None);self.session.pop('booking',None)
            return self.result('Pedido descartado. Nenhuma consulta existente foi cancelada.')
        patient=customer_patient(self.repo,self.user)
        professionals=[p for p in self.repo.list('professionals',self.user['empresa_id']) if p['ativo']]
        if not professionals: return self.result('A equipe precisa cadastrar a disponibilidade dos profissionais antes de reservar. Sua mensagem está registrada.')
        if not state:
            surgical=any(t in m for t in ('cirurg','complex','siso','implante'))
            procedure='Avaliação cirúrgica' if surgical else 'Limpeza dental (profilaxia)' if 'limpeza' in m else 'Consulta de avaliação'
            candidates=[p for p in professionals if procedure in p['procedimentos']]
            if not candidates: return self.result('A equipe precisa confirmar qual profissional atende essa solicitação.')
            p=candidates[0]
            if 'elias' in m or 'roberto' in m:
                named=[v for v in candidates if normalized(v['nome']) in m]
                if not named:return self.result('O profissional indicado não atende esse procedimento no cadastro. Escolha uma avaliação ou consulte a equipe.')
                p=named[0]
            state=dict(professional_id=p['id'],procedure=procedure)
            self.session['patient_booking']=state
            self.session.pop('booking',None)
            today=datetime.now(LOCAL_ZONE).date()
            dates=[]
            for offset in range(1,8):
                day=(today+timedelta(days=offset)).isoformat();slots=available(self.repo,self.user['empresa_id'],p['id'],day,p['duracao_padrao'],patient['id'])
                if slots: dates.append(datetime.strptime(day,'%Y-%m-%d').strftime('%d/%m/%Y')+' — '+', '.join(slots[:5]))
            prefix='Para avaliar a necessidade de cirurgia, ' if surgical else ''
            intro=prefix+f"posso preparar {procedure.lower()} com {p['nome']}. Não confirmo indicação de cirurgia pelo chat. " if surgical else f"Posso preparar {procedure.lower()} com {p['nome']}. "
            if not dates:return self.result('Não encontrei horários livres nos próximos sete dias. A equipe verificará outras datas.')
            prompt=intro+'Horários livres cadastrados (confirmação sujeita a nova verificação):\n'+'\n'.join(dates)+'\nEscolha uma data e um único horário. Depois da prévia, confirme para salvar na agenda.'
            # Accept a full initial request too, but never skip its confirmation.
            if not re.search(r'\d{1,2}(?:h|:)',m):return self.result(prompt)
        p=record(self.repo,'professionals',self.user['empresa_id'],state['professional_id'])
        booking=SchedulingAgent(self.repo,self.user,self.session)
        if m not in ('confirmar','confirmo','sim','pode agendar'):
            existing=self.session.get('booking')
            if not existing:
                self.session['booking']=dict(user=self.user['id'],clinic=self.user['empresa_id'],time=datetime.now(LOCAL_ZONE).timestamp(),data=dict(paciente_id=patient['id'],procedimento=state['procedure'],dentista=p['nome'],duracao=p['duracao_padrao']),key=uuid4().hex)
            # A patient can supply dates/times, never another patient's name or arbitrary fields.
            from booking_input import patient_datetime
            try: choice=patient_datetime(m)
            except ValueError as error:
                current=self.session.get('booking',{});current.pop('ready',None);self.session['booking']=current
                return self.result(str(error))
            if not choice:return self.result('Informe somente a data e o horário desejados, ou diga cancelar. Exemplo: amanhã às 10h.')
            result=booking.respond(choice)
        else: result=booking.respond(m)
        if result is None:return self.result('O pedido expirou. Peça novamente para agendar.')
        if result.get('estado')=='erro':
            current=self.session.get('booking',{}).get('data',{});day=current.get('data')
            slots=available(self.repo,self.user['empresa_id'],p['id'],day,p['duracao_padrao'],patient['id']) if day else []
            if slots: result['resposta']+=' Horários livres nessa data: '+', '.join(slots[:8])+'.'
        if result.get('estado')=='concluido':self.session.pop('patient_booking',None)
        return result

    @staticmethod
    def result(text):return dict(resposta=text,fontes=[],gerado_por_llm=False,tipo='agendamento')
