"""Validated scheduling tools. No model, SQL, or clinical decisions here."""
import re
import unicodedata
from datetime import datetime, timedelta
from uuid import uuid4
from management import LOCAL_ZONE
from services import Appointment, ClinicRecords


class AppointmentConflict(ValueError):
    pass


def normalized(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c)).split())


def check_conflict(existing, data, identifier=None):
    """Shared by both repositories, under their respective transaction locks."""
    if data['status'] == 'cancelado':
        return
    start = sum(int(v) * n for v, n in zip(data['horario'].split(':')[:2], (60, 1)))
    end = start + data['duracao']
    if end > 1440:
        raise AppointmentConflict('A consulta não pode terminar em outro dia. Ajuste o horário ou a duração.')
    for row in existing:
        if row['id'] == identifier or row['status'] == 'cancelado' or row['data'] != data['data']:
            continue
        other = sum(int(v) * n for v, n in zip(row['horario'].split(':')[:2], (60, 1)))
        if start < other + row['duracao'] and other < end:
            doctor=lambda name: re.sub(r'^(?:dra?|doutora?)\.?\s+', '', normalized(name))
            if doctor(row['dentista']) == doctor(data['dentista']):
                raise AppointmentConflict('Esse profissional já tem uma consulta nesse intervalo. Escolha outro horário.')
            if row['paciente_id'] == data['paciente_id']:
                raise AppointmentConflict('O paciente já tem uma consulta nesse intervalo. Escolha outro horário.')


class SchedulingAgent:
    """A bounded, explicit conversation flow; only the authenticated owner can confirm."""
    fields = ('paciente_id', 'data', 'horario', 'procedimento', 'dentista', 'duracao')
    questions = {
        'paciente_id': 'Qual é o nome do paciente cadastrado?',
        'data': 'Para qual data? Pode dizer amanhã ou informar DD/MM/AAAA.',
        'horario': 'Em qual horário? Por exemplo, 16h ou 16:30.',
        'procedimento': 'Qual procedimento deseja agendar? Por exemplo, consulta de avaliação ou limpeza.',
        'dentista': 'Com qual profissional? Informe o nome usado na agenda da clínica.',
        'duracao': 'Qual a duração em minutos? Por exemplo, 30 minutos.',
    }

    def __init__(self, repository, user, session, now=None):
        self.repository, self.user, self.session = repository, user, session
        self.records = ClinicRecords(repository, user['empresa_id'])
        self.now = now or datetime.now(LOCAL_ZONE)

    def respond(self, text):
        message = normalized(text)
        state = self.session.get('booking')
        if state and (state['user'] != self.user['id'] or state['clinic'] != self.user['empresa_id'] or self.now.timestamp() - state['time'] > 1800):
            self.session.pop('booking', None)
            state = None
        intent = bool(re.search(r'\b(agende|agendar|marque|marcar)\b', message))
        if message in ('cancelar', 'cancelar agendamento', 'desistir') and state:
            self.session.pop('booking', None)
            return self.result('Rascunho descartado. Nenhuma consulta existente foi cancelada.', 'cancelado')
        if not state and not intent:
            return None
        if not getattr(self.repository, 'supports_booking_receipts', False):
            return self.result('O agendamento pelo assistente ainda requer integração de confirmações persistentes com PostgreSQL. Use o formulário da agenda; não fiz alterações.', 'indisponivel')
        if state and state.get('done') and message in ('confirmar', 'confirmo', 'sim', 'pode agendar'):
            return self.result('Essa confirmação já foi processada. Confira o agendamento na agenda; nenhuma nova consulta foi criada.', 'concluido', state['done'])
        if state and state.get('done') and not intent:
            return None
        if not state or state.get('done'):
            state = dict(user=self.user['id'], clinic=self.user['empresa_id'], time=self.now.timestamp(), data={}, key=uuid4().hex)
        data = state['data']
        if message in ('confirmar', 'confirmo', 'sim', 'pode agendar'):
            if not state.get('ready'):
                return self.result('Precisamos completar os dados e revisar o agendamento antes de confirmar.', 'coletando')
            try:
                model = Appointment(**data, status='confirmado')
                self.validate_future(model)
                if self.records.get('patients',model.paciente_id)['status']=='inativo': raise ValueError('Paciente inativo')
                created = self.records.save('appointments', model, operation_key=f"{self.user['id']}:{state['key']}")
            except (AppointmentConflict, ValueError, LookupError) as error:
                state.pop('ready', None)
                self.session['booking'] = state
                return self.result(str(error) if isinstance(error, AppointmentConflict) else 'Não foi possível gravar. Confira paciente, data e campos obrigatórios. Nenhuma nova consulta foi criada.', 'erro')
            state['done'] = created['id']
            self.session['booking'] = state
            return self.result(f"Confirmação processada: {self.description(created)}. Número {created['id']}, situação atual: {created['status']}. Confira na agenda.", 'concluido', created['id'])

        old = dict(data)
        waiting = state.get('waiting')
        name = re.search(r'(?:para (?:o |a )?|paciente )(.+?)(?=\s+(?:amanha|hoje|dia|as|em|com|\d{4}-)|$)', message)
        if name and 'paciente_id' in data and not (intent or 'paciente ' in message): name=None
        if name: data.pop('paciente_id',None)
        try:
            self.extract(text, message, data, waiting)
        except ValueError:
            state.pop('ready',None)
            self.session['booking']=state
            return self.result('Não consegui interpretar a data, horário ou duração. Use uma data válida, horário como 16:30 e duração em minutos.', 'coletando')
        if getattr(self.repository,'supports_workflows',False):
            profiles=[p for p in self.repository.list('professionals',self.user['empresa_id']) if p['ativo']]
            if any(t in message for t in ('cirurg','procedimento complicado','procedimento complexo')):
                data['procedimento']='Avaliação cirúrgica'
            if profiles:
                aliases={'limpeza':'Limpeza dental (profilaxia)','profilaxia':'Limpeza dental (profilaxia)','avaliacao':'Consulta de avaliação','consulta':'Consulta de avaliação','canal':'Tratamento de canal','clareamento':'Clareamento dental','cirurgia':'Avaliação cirúrgica'}
                selected=aliases.get(normalized(data.get('procedimento','')))
                if selected:data['procedimento']=selected
            compatible=[p for p in profiles if normalized(data.get('procedimento','')) in {normalized(v) for v in p['procedimentos']}]
            if len(compatible)==1 and 'dentista' not in data:
                data['dentista']=compatible[0]['nome'];data['duracao']=compatible[0]['duracao_padrao']
            if profiles and 'dentista' in data:
                selected=[p for p in profiles if normalized(p['nome'])==normalized(data['dentista']).removeprefix('dr. ').removeprefix('dra. ')]
                if len(selected)==1:data['duracao']=data.get('duracao',selected[0]['duracao_padrao'])
        patients = [p for p in self.records.list('patients') if p['status'] != 'inativo']
        if 'paciente_id' not in data:
            candidate = state.get('patient_name')
            if name: candidate = name.group(1).strip(' .')
            elif waiting == 'paciente_id': candidate = message.strip(' .')
            if candidate:
                matches = [p for p in patients if candidate == normalized(p['nome']) or candidate in normalized(p['nome'])]
                if message.isdigit() and state.get('candidates'):
                    matches = [p for p in patients if p['id'] == int(message) and p['id'] in state['candidates']]
                if len(matches) == 1:
                    data['paciente_id'] = matches[0]['id']
                    state.pop('candidates', None)
                else:
                    state['waiting'] = 'paciente_id'
                    state['candidates'] = [p['id'] for p in matches[:10]]
                    self.session['booking'] = state
                    options = '; '.join(f"{p['id']}: {p['nome']}" for p in matches[:10])
                    return self.result(('Encontrei mais de um paciente. Informe o nome completo ou o número: ' + options) if matches else 'Não encontrei esse paciente ativo na sua clínica. Informe o nome completo cadastrado.', 'coletando')
        if data != old:
            state.pop('ready', None)
            state['key'] = uuid4().hex
        missing = next((key for key in self.fields if key not in data), None)
        if missing:
            state['waiting'] = missing
            self.session['booking'] = state
            return self.result(self.questions[missing] + ' Nada foi agendado ainda.', 'coletando')
        try:
            model = Appointment(**data, status='confirmado')
            self.validate_future(model)
            self.records.get('patients', model.paciente_id)
            if getattr(self.repository,'supports_workflows',False):
                from professionals import validate_professional
                validate_professional(self.repository.list('professionals',self.user['empresa_id']),model.model_dump(mode='json',exclude_none=True))
            check_conflict(self.records.list('appointments'), model.model_dump(mode='json'))
        except (ValueError, LookupError) as error:
            state.pop('ready', None)
            self.session['booking'] = state
            return self.result(str(error) if isinstance(error, AppointmentConflict) else 'Confira os dados. A data deve ser futura, o horário válido e a duração deve ser de 1 a 1440 minutos. Você pode corrigir, por exemplo: amanhã às 17h.', 'erro')
        state['ready'] = True
        state.pop('waiting', None)
        self.session['booking'] = state
        return self.result('Confira: ' + self.description(data) + '. Não há conflito nos registros atuais; confira também a disponibilidade do profissional. Digite “confirmar” para gravar, corrija os dados ou digite “cancelar”. Ainda não agendei.', 'aguardando_confirmacao')

    def validate_future(self, model):
        if datetime.combine(model.data, model.horario, tzinfo=LOCAL_ZONE) <= self.now:
            raise ValueError('Data passada')

    def description(self, data):
        patient = self.records.get('patients', data['paciente_id'])
        return f"{patient['nome']}, {data['data'][8:10]}/{data['data'][5:7]}/{data['data'][:4]} às {data['horario'][:5]}, {data['procedimento']}, {data['dentista']}, {data['duracao']} minutos"

    def extract(self, original, message, data, waiting):
        from booking_input import normalize_separators
        message=normalize_separators(message)
        date_match = re.search(r'(?<![\d/\-])(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{4})?)(?![\d/\-])', message)
        if date_match:
            value = date_match.group(1)
            if '/' in value:
                parts = value.split('/')
                value = f"{parts[2] if len(parts)>2 else self.now.year}-{int(parts[1]):02}-{int(parts[0]):02}"
            data['data'] = datetime.strptime(value, '%Y-%m-%d').date().isoformat()
        elif re.search(r'\d\s*/',message):
            raise ValueError('Data incompleta ou inválida')
        elif re.search(r'\b(amanha|hoje)\b', message):
            offset=2 if 'depois de amanha' in message else int('amanha' in message)
            data['data'] = (self.now.date()+timedelta(days=offset)).isoformat()
        hour = re.search(r'\b(\d{1,2})(?:h(?:(\d{2}))?|:(\d{2}))\b', message)
        if hour:
            data['horario'] = f"{int(hour.group(1)):02}:{hour.group(2) or hour.group(3) or '00'}"
        elif waiting == 'horario' and message.isdigit():
            data['horario'] = f'{int(message):02}:00'
        duration = re.search(r'\b(\d+)\s*(?:minutos|min)\b', message)
        if duration: data['duracao'] = int(duration.group(1))
        elif waiting == 'duracao' and message.isdigit(): data['duracao'] = int(message)
        # Free text is accepted only in the field explicitly asked for, or with a label.
        procedure = re.search(r'procedimento\s*[:=]?\s*(.+?)(?=\s+(?:com |duracao|por \d|\d+ minutos)|$)', original, re.I)
        dentist = re.search(r'(?:dentista\s*[:=]?|com\s+(?=dr|dra))\s*(.+?)(?=\s+(?:procedimento|dura[çc][aã]o|amanh[aã]|hoje|por \d|\d+ minutos)|$)', original, re.I)
        if procedure: data['procedimento'] = procedure.group(1).strip()
        elif waiting == 'procedimento' and not (hour or date_match or duration or message in ('amanha','hoje')): data['procedimento'] = original.strip()
        else:
            from catalog import PROCEDURE_OPTIONS
            for option in PROCEDURE_OPTIONS:
                if normalized(option) in message:
                    data['procedimento']=option
                    break
            if re.search(r'\b(?:agende|agendar|marque|marcar)\s+(?:uma?\s+)?limpeza\b',message):
                data['procedimento']=PROCEDURE_OPTIONS[1]
        if dentist: data['dentista'] = dentist.group(1).strip()
        elif waiting == 'dentista' and not (hour or date_match or duration or message in ('amanha','hoje')): data['dentista'] = original.strip()
        elif re.match(r'^dra?\.?\s+\S',message): data['dentista']=original.strip()
        if any(len(data.get(key,''))>200 for key in ('procedimento','dentista')):
            data.pop('procedimento',None);data.pop('dentista',None)
            raise ValueError('Texto excessivo')

    @staticmethod
    def result(text, state, appointment_id=None):
        return dict(resposta=text, origem='agendamento', estado=state, agendamento_id=appointment_id,
                    gerado_por_llm=False, fontes=[], acoes=[dict(rotulo='Conferir agenda', url='/agendamentos')])
