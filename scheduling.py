"""Validated scheduling tools. No model, SQL, or clinical decisions here."""
import re
import unicodedata
from datetime import datetime, timedelta
from uuid import uuid4
from management import LOCAL_ZONE
from services import Appointment, ClinicRecords
from booking_input import BOOKING_INTENT, NAMED_DAY, named_date, patient_datetime

RESUME_BOOKING = 'continuar agendamento'
CONFIRM_WORDS = frozenset({'confirmar', 'confirmo', 'sim', 'pode agendar'})
# Respostas curtas que só valem como confirmação quando o rascunho já foi revisado e está pronto.
EASY_CONFIRM_WORDS = CONFIRM_WORDS | frozenset({
    'ok', 'okay', 'okk', 'ok pode', 'ok pode agendar', 'ok pode marcar', 'ok confirma', 'ok confirmar',
    'pode', 'pode sim', 'pode marcar', 'pode confirmar', 'sim pode agendar', 'sim pode', 'confirma', 'confirmado',
    'agende', 'agenda', 'agendar', 'marca', 'marcar', 'isso', 'beleza', 'fechado', 'perfeito', 'certo', 'ta bom',
    'tudo certo', 'claro', 'positivo', 'manda', 'vai',
})


def confirmation_text(message):
    return ' '.join(re.sub(r'[^\w ]', ' ', message).split())


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
    fields = ('paciente_id', 'procedimento', 'dentista', 'data', 'horario', 'duracao')
    questions = {
        'paciente_id': 'Para qual paciente? Escolha abaixo ou digite parte do nome.',
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

    def active_state(self):
        state = self.session.get('booking')
        if state and (state['user'] != self.user['id'] or state['clinic'] != self.user['empresa_id'] or self.now.timestamp() - state['time'] > 1800):
            self.session.pop('booking', None)
            return None
        return state

    def respond(self, text):
        message = normalized(text).strip('!?., ')
        state = self.active_state()
        intent = bool(BOOKING_INTENT.search(message))
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
        loose = confirmation_text(message)
        if message in CONFIRM_WORDS or (state.get('ready') and loose in EASY_CONFIRM_WORDS):
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
                return self.result(str(error) if isinstance(error, AppointmentConflict) else 'Não foi possível gravar. Confira paciente, data e campos obrigatórios. Nenhuma nova consulta foi criada.', 'erro',
                                   options=self.slot_options(data))
            state['done'] = created['id']
            self.session['booking'] = state
            reply = self.result(f"Agendado com sucesso: {self.description(created)}. Número {created['id']}, situação atual: {created['status']}.", 'concluido', created['id'])
            reply['agendado'] = True
            return reply

        old = dict(data)
        waiting = state.get('waiting')
        name = re.search(r'(?:para (?:o |a )?|paciente (?:para (?:o |a )?)?)(.+?)(?=\s+(?:'+NAMED_DAY+r'|dia|as|em|com|\d{4}-)\b|$)', message)
        patient_choice = re.fullmatch(r'paciente\s+#?(\d+)', message)
        correcting_patient = re.match(r'^(?:mude|troque|corrija|altere|ajuste) (?:o )?paciente\b',message)
        if name and not (intent or message.startswith('paciente ') or correcting_patient or waiting == 'paciente_id'): name=None
        if (name or patient_choice) and message != RESUME_BOOKING:
            data.pop('paciente_id',None)
        if message != RESUME_BOOKING:
            try:
                self.extract(text, message, data, waiting)
            except ValueError as error:
                state['data'] = old
                state.pop('ready',None)
                self.session['booking']=state
                return self.result(str(error), 'erro', options=self.slot_options(old))
        if getattr(self.repository,'supports_workflows',False):
            profiles=[p for p in self.repository.list('professionals',self.user['empresa_id']) if p['ativo']]
            named_professional = next((p for p in profiles if re.search(
                r'\bcom (?:o |a )?'+re.escape(normalized(p['nome']))+r'\b', message
            ) or re.fullmatch(
                r'(?:mude|troque|corrija|altere|ajuste) (?:o dentista |o profissional )?para '+re.escape(normalized(p['nome'])),
                message,
            )),None)
            if named_professional:
                data['dentista'] = named_professional['nome']
            if any(t in message for t in ('cirurg','procedimento complicado','procedimento complexo')):
                data['procedimento']='Avaliação cirúrgica'
            if profiles:
                aliases={'limpeza':'Limpeza dental (profilaxia)','profilaxia':'Limpeza dental (profilaxia)','avaliacao':'Consulta de avaliação','consulta':'Consulta de avaliação','canal':'Tratamento de canal','clareamento':'Clareamento dental','cirurgia':'Avaliação cirúrgica'}
                selected=aliases.get(normalized(data.get('procedimento','')))
                if selected:data['procedimento']=selected
            compatible=[p for p in profiles if normalized(data.get('procedimento','')) in {normalized(v) for v in p['procedimentos']}]
            if 'procedimento' in data and profiles and not compatible:
                data.pop('procedimento', None)
                state['waiting'] = 'procedimento'
                state.pop('ready', None)
                self.session['booking'] = state
                return self.result('Esse procedimento não está na agenda dos profissionais ativos. Escolha um procedimento disponível.',
                                   'coletando', options=self.step_options('procedimento', data, []))
            if compatible and data.get('dentista') and all(
                normalized(data['dentista']).removeprefix('dr. ').removeprefix('dra. ') != normalized(p['nome'])
                for p in compatible
            ):
                data.pop('dentista', None)
                data.pop('duracao', None)
                state['waiting'] = 'dentista'
                state.pop('ready', None)
                self.session['booking'] = state
                return self.result('Para esse procedimento, escolha um profissional da lista.', 'coletando',
                                   options=self.step_options('dentista', data, []))
            if len(compatible)==1 and 'dentista' not in data:
                data['dentista']=compatible[0]['nome'];data['duracao']=compatible[0]['duracao_padrao']
            if profiles and 'dentista' in data:
                selected=[p for p in profiles if normalized(p['nome'])==normalized(data['dentista']).removeprefix('dr. ').removeprefix('dra. ')]
                if len(selected)==1:
                    data['dentista'] = selected[0]['nome']
                    changed = old.get('dentista') and old['dentista'] != data['dentista']
                    if 'duracao' not in data or (changed and not re.search(r'\b\d+\s*(?:minutos|min)\b', message)):
                        data['duracao'] = selected[0]['duracao_padrao']
        patients = [p for p in self.records.list('patients') if p['status'] != 'inativo']
        if 'paciente_id' not in data and message != RESUME_BOOKING:
            candidate = name.group(1).strip(' .') if name else ''
            if not candidate and waiting == 'paciente_id' and not intent and data == old:
                candidate = message.strip(' .')
            if candidate or patient_choice:
                matches = [p for p in patients if candidate and candidate in normalized(p['nome'])]
                if patient_choice or candidate.isdigit():
                    identifier = int(patient_choice.group(1) if patient_choice else candidate)
                    matches = [p for p in patients if p['id'] == identifier]
                if len(matches) == 1:
                    data['paciente_id'] = matches[0]['id']
                else:
                    state['waiting'] = 'paciente_id'
                    state.pop('ready', None)
                    self.session['booking'] = state
                    prompt = ('Encontrei mais de um paciente. Escolha uma opção ou digite o nome completo.' if matches
                              else 'Não encontrei um paciente ativo com esse nome. Tente parte do nome ou escolha na lista.')
                    return self.result(prompt, 'coletando', options=self.patient_options(matches or patients))
        if data != old:
            state.pop('ready', None)
            state['key'] = uuid4().hex
        missing = next((key for key in self.fields if key not in data), None)
        if missing:
            state['waiting'] = missing
            self.session['booking'] = state
            options = self.step_options(missing, data, patients)
            prompt = self.questions[missing]
            if missing == 'paciente_id' and not patients:
                prompt = 'Cadastre um paciente ativo na tela Pacientes para continuar.'
            return self.result(prompt + ' Nada foi agendado ainda.', 'coletando', options=options)
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
            return self.result(str(error) if isinstance(error, AppointmentConflict) else 'Confira a data, o horário e a duração. Você pode corrigir, por exemplo: amanhã às 17h.', 'erro',
                               options=self.slot_options(data))
        state['ready'] = True
        state.pop('waiting', None)
        self.session['booking'] = state
        return self.result('Confira: ' + self.description(data) + '. Você pode confirmar, cancelar ou corrigir. Ainda não agendei.', 'aguardando_confirmacao',
                           options=[self.option('Confirmar agendamento', 'confirmar'), self.option('Cancelar rascunho', 'cancelar')])

    def validate_future(self, model):
        if datetime.combine(model.data, model.horario, tzinfo=LOCAL_ZONE) <= self.now:
            raise ValueError('Data passada')

    def description(self, data):
        patient = self.records.get('patients', data['paciente_id'])
        return f"{patient['nome']}, {data['data'][8:10]}/{data['data'][5:7]}/{data['data'][:4]} às {data['horario'][:5]}, {data['procedimento']}, {data['dentista']}, {data['duracao']} minutos"

    @staticmethod
    def option(label, message):
        return dict(rotulo=label, mensagem=message)

    def patient_options(self, patients):
        return [self.option(f"{p['nome']} (#{p['id']})", f"paciente #{p['id']}") for p in patients[:6]]

    def step_options(self, field, data, patients):
        if field == 'paciente_id':
            return self.patient_options(patients)
        profiles = [p for p in self.repository.list('professionals', self.user['empresa_id']) if p['ativo']]
        if field == 'procedimento':
            procedures = list(dict.fromkeys(procedure for p in profiles for procedure in p['procedimentos']))
            preferred = ('Consulta de avaliação', 'Limpeza dental (profilaxia)')
            ordered = [v for v in preferred if v in procedures] + [v for v in procedures if v not in preferred]
            return [self.option(value, f'procedimento: {value}') for value in ordered[:8]]
        if field == 'dentista':
            return [self.option(p['nome'], 'dentista: '+p['nome']) for p in profiles
                    if normalized(data.get('procedimento','')) in {normalized(v) for v in p['procedimentos']}][:6]
        if field == 'data':
            return [self.option(label, day) for label, day in
                    [('Hoje', 'hoje'), ('Amanhã', 'amanhã'), ('Depois de amanhã', 'depois de amanhã')]]
        return self.slot_options(data) if field == 'horario' else []

    def slot_options(self, data):
        from professionals import available

        clinic = self.user['empresa_id']
        profile = next((p for p in self.repository.list('professionals', clinic)
                        if p['ativo'] and normalized(p['nome']) == normalized(data.get('dentista',''))), None)
        if not profile or not data.get('data') or self.user.get('role') == 'customer':
            return []
        start = max(self.now.date(), datetime.fromisoformat(data['data']).date())
        options = []
        for offset in range(8):
            day = start + timedelta(days=offset)
            slots = available(self.repository,clinic,profile['id'],day.isoformat(),
                              data.get('duracao',profile['duracao_padrao']),data.get('paciente_id',-1),now=self.now)
            options.extend(self.option(f'{day:%d/%m} às {slot}', f'{day:%d/%m/%Y} às {slot}') for slot in slots[:3])
            if len(options) >= 6:
                break
        return options[:6]

    def extract(self, original, message, data, waiting):
        from catalog import requested_procedure

        date_time = '' if re.match(r'^(?:procedimento|dentista)\s*:', message) else patient_datetime(message)
        hour = re.search(r'(?:^| )(\d{2}:\d{2})$', date_time)
        value = date_time[:hour.start()].strip() if hour else date_time
        if value:
            if '/' in value:
                parts = value.split('/')
                value = f"{parts[2] if len(parts)>2 else self.now.year}-{int(parts[1]):02}-{int(parts[0]):02}"
            date = datetime.strptime(value, '%Y-%m-%d').date() if value[0].isdigit() else named_date(value, self.now.date())
            data['data'] = date.isoformat()
        if hour:
            data['horario'] = hour.group(1)
        elif waiting == 'horario' and message.isdigit():
            data['horario'] = f'{int(message):02}:00'
        duration = re.search(r'\b(\d+)\s*(?:minutos|min)\b', message)
        if duration: data['duracao'] = int(duration.group(1))
        elif waiting == 'duracao' and message.isdigit(): data['duracao'] = int(message)
        # Free text is accepted only in the field explicitly asked for, or with a label.
        procedure = re.search(r'procedimento\s*[:=]?\s*(.+?)(?=\s+(?:com |duracao|por \d|\d+ minutos)|$)', original, re.I)
        dentist = re.search(r'(?:dentista\s*[:=]?|com\s+(?=dr|dra))\s*(.+?)(?=\s+(?:procedimento|dura[çc][aã]o|amanh[aã]|hoje|por \d|\d+ minutos)|$)', original, re.I)
        if procedure: data['procedimento'] = procedure.group(1).strip()
        elif not message.startswith('paciente '):
            if candidate := requested_procedure(message):
                data['procedimento'] = candidate
            elif waiting == 'procedimento' and not (date_time or duration or dentist):
                data['procedimento'] = original.strip()
        if dentist: data['dentista'] = dentist.group(1).strip()
        elif waiting == 'dentista' and not (date_time or duration or procedure or message.startswith('paciente ')):
            data['dentista'] = original.strip()
        elif re.match(r'^dra?\.?\s+\S',message): data['dentista']=original.strip()
        if any(len(data.get(key,''))>200 for key in ('procedimento','dentista')):
            data.pop('procedimento',None);data.pop('dentista',None)
            raise ValueError('Texto excessivo')

    @staticmethod
    def result(text, state, appointment_id=None, *, options=None):
        action = (dict(rotulo='Ver no calendário', url=f'/agendamentos?agendamento_id={appointment_id}') if appointment_id
                  else dict(rotulo='Conferir agenda', url='/agendamentos'))
        return dict(resposta=text, origem='agendamento', estado=state, agendamento_id=appointment_id,
                    gerado_por_llm=False, fontes=[], acoes=[action], opcoes=options or [])
