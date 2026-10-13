"""Regras independentes do adaptador de banco."""
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

class Article(BaseModel):
    model_config = ConfigDict(extra='forbid')
    titulo: str = Field(min_length=1,max_length=200)
    categoria: str = Field(min_length=1,max_length=100)
    conteudo: str = Field(min_length=1,max_length=20000)
    status: bool = True

    @field_validator('titulo','categoria','conteudo')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Campo vazio')
        return value.strip()

class Stock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nome: str = Field(min_length=1,max_length=200)
    categoria: str = Field(min_length=1,max_length=100)
    unidade: str = Field(min_length=1,max_length=100)
    quantidade: StrictInt = Field(ge=0,le=1000000000)
    minimo: StrictInt = Field(ge=0,le=1000000000)

    @field_validator('nome','categoria','unidade')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Campo vazio')
        return value.strip()

class Movement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    delta: StrictInt = Field(ge=-1000000000,le=1000000000)

    @field_validator('delta')
    @classmethod
    def nonzero(cls,value):
        if value == 0:
            raise ValueError('Movimentação deve ser diferente de zero')
        return value

def stock_view(data):
    return dict(data,status='esgotado' if data['quantidade']==0 else 'baixo' if data['quantidade']<data['minimo'] else 'ok')

class ClinicService:
    def __init__(self, repository, clinic):
        self.repository = repository
        self.clinic = clinic

    def articles(self):
        return self.repository.list('kb',self.clinic)

    def save_article(self, article, identifier=None):
        existing = next((a for a in self.articles() if a['id']==identifier),None)
        if identifier is not None and existing is None:
            raise LookupError('Registro não encontrado')
        data = article.model_dump()
        data.update(views=existing.get('views',0) if existing else 0,
                    atualizado=datetime.now(timezone.utc).strftime('%d/%m/%Y'))
        return self.repository.save('kb',self.clinic,data,identifier)

    def stocks(self):
        return [stock_view(s) for s in self.repository.list('stock',self.clinic)]

    def save_stock(self, stock, identifier=None):
        return stock_view(self.repository.save('stock',self.clinic,stock.model_dump(),identifier))

    def move(self, identifier, delta):
        return stock_view(self.repository.move(self.clinic,identifier,delta))

from datetime import date, time
from typing import Literal

class Patient(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    nome: str = Field(min_length=1,max_length=200)
    telefone: str = Field(max_length=40,default='')
    email: str = Field(max_length=254,default='')
    status: Literal['ativo','novo','inativo'] = 'novo'
    plano: str = Field(max_length=100,default='')
    ultima_consulta: date | None = None
    proxima_consulta: date | None = None
    procedimentos: StrictInt = Field(ge=0,default=0)

    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        if value and ('@' not in value or '.' not in value.split('@')[-1]):
            raise ValueError('E-mail inválido')
        return value

class Appointment(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    paciente_id: StrictInt = Field(gt=0)
    data: date
    horario: time
    duracao: StrictInt = Field(ge=1,le=1440)
    procedimento: str = Field(min_length=1,max_length=200)
    dentista: str = Field(min_length=1,max_length=200)
    status: Literal['confirmado','pendente','cancelado'] = 'pendente'

class Attendance(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    cliente: str = Field(min_length=1,max_length=200)
    preview: str = Field(min_length=1,max_length=2000)
    status: Literal['resolved','pending','escalated'] = 'pending'
    canal: Literal['human','ai'] = 'human'

class HumanMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    texto: str = Field(min_length=1,max_length=4000)

class ClinicRecords:
    """CRUD administrativo provisório sem SQL nas regras de negócio."""
    models = {'patients':Patient,'appointments':Appointment,'attendance':Attendance}

    def __init__(self,repository,clinic):
        self.repository,self.clinic = repository,clinic

    def list(self,kind):
        records = self.repository.list(kind,self.clinic)
        if kind == 'appointments':
            patients = {p['id']:p['nome'] for p in self.repository.list('patients',self.clinic)}
            return [dict(r,paciente=patients.get(r['paciente_id'],'Paciente removido')) for r in records]
        return records

    def get(self,kind,identifier):
        record = next((r for r in self.list(kind) if r['id']==identifier),None)
        if record is None: raise LookupError('Registro não encontrado')
        return record

    def save(self,kind,model,identifier=None):
        existing = self.get(kind,identifier) if identifier is not None else {}
        data = model.model_dump(mode='json')
        if kind == 'patients':
            data.update(iniciais=''.join(p[0] for p in data['nome'].split())[:2].upper(),cor='#0284c7')
        elif kind == 'appointments':
            self.get('patients',data['paciente_id'])
            data['cor'] = '#0284c7'
        else:
            data.update(iniciais=''.join(p[0] for p in data['cliente'].split())[:2].upper(),cor='',
                        hora=existing.get('hora',datetime.now().strftime('%H:%M')),
                        mensagens=existing.get('mensagens',[]))
        data['criado_em'] = existing.get('criado_em',datetime.now(timezone.utc).isoformat())
        return self.repository.save(kind,self.clinic,data,identifier)

    def delete(self,kind,identifier):
        self.get(kind,identifier)
        if kind == 'patients' and any(a['paciente_id']==identifier for a in self.list('appointments')):
            raise ValueError('Paciente possui agendamentos; remova-os primeiro ou marque o paciente como inativo')
        self.repository.delete(kind,self.clinic,identifier)
