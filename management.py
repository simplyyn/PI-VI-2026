"""RF004/RF006: resumos persistidos e indicadores calculados, sem dados demonstrativos."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from analysis import attendance_version
from services import ClinicRecords, ComplaintService

try:
    LOCAL_ZONE = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:
    LOCAL_ZONE = timezone(timedelta(hours=-3))


QUESTION_TOPICS = (
    ('Preços e pagamentos', r'\b(?:precos?|cust[ao]\w*|orcamento|pagamento|valor|pix)\b'),
    ('Convênios', r'\b(?:convenios?|planos?|unimed)\b'),
    ('Cancelamento e remarcação', r'\b(?:cancel\w*|remarc\w*|reagend\w*)\b'),
    ('Agenda e horários', r'\b(?:agend\w*|horarios?|marcar|disponibilidade|expediente)\b'),
    ('Procedimentos', r'\b(?:procedimentos?|limpeza|canal|implante|extracao|clareamento|avaliacao|restauracao)\b'),
)
QUESTION_WORDS = re.compile(r'\b(?:qual|quais|quanto|quantas|quantos|como|quando|onde|aceita\w*|atende\w*|abre|fecha)\b')


def message_stamp(message):
    try:
        stamp = datetime.fromisoformat(message['criado_em'])
    except (KeyError, TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def conversation_metrics(attendances, dates):
    from assistant import normalize

    topics = Counter()
    samples = []
    for attendance in attendances:
        waiting = None
        for message in attendance.get('mensagens', []):
            stamp = message_stamp(message)
            if stamp is None:
                continue
            if message['autor'] == 'client':
                in_period = stamp.astimezone(LOCAL_ZONE).date() in dates
                text = normalize(message['texto'])
                if in_period and ('?' in message['texto'] or QUESTION_WORDS.search(text)):
                    for title, pattern in QUESTION_TOPICS:
                        if re.search(pattern, text):
                            topics[title] += 1
                            break
                if waiting is None:
                    waiting = stamp
            elif waiting is not None and message['autor'] in {'ai', 'human'} and message.get('responde', True) and stamp >= waiting:
                if waiting.astimezone(LOCAL_ZONE).date() in dates:
                    samples.append((stamp - waiting).total_seconds())
                waiting = None
    return dict(tempo_resposta=round(sum(samples) / len(samples)) if samples else None,
                amostras_tempo_resposta=len(samples), principais_duvidas=[dict(tema=label, total=count) for label, count in topics.most_common()])

class SummaryService:
    def __init__(self,repository,clinic):
        self.repository,self.clinic=repository,clinic

    def get(self,identifier):
        attendance=ClinicRecords(self.repository,self.clinic).get('attendance',identifier)
        saved=next((s for s in self.repository.list('summaries',self.clinic) if s['attendance_id']==identifier),None)
        return dict(saved,desatualizado=saved['versao']!=attendance_version(attendance)) if saved else None

    def generate(self,identifier,summarizer):
        attendance=ClinicRecords(self.repository,self.clinic).get('attendance',identifier)
        saved=self.get(identifier)
        if saved and not saved['desatualizado']:
            return saved
        text=summarizer.summarize(attendance)
        data=dict(resumo=text,modelo=summarizer.model,gerado_em=datetime.now(timezone.utc).isoformat(),versao=attendance_version(attendance))
        self.repository.set_summary(self.clinic,identifier,data)
        return self.get(identifier)

class ManagementReport:
    def __init__(self,repository,clinic):
        self.repository,self.clinic=repository,clinic

    def build(self,dias=7):
        now=datetime.now(LOCAL_ZONE)
        dates=[(now-timedelta(days=i)).date() for i in reversed(range(dias))]
        daily={day.isoformat():{'ia':0,'humano':0} for day in dates}
        attendances=[]
        all_attendances = self.repository.list('attendance', self.clinic)
        for attendance in all_attendances:
            try:
                stamp=datetime.fromisoformat(attendance['criado_em'])
                if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
                day=stamp.astimezone(LOCAL_ZONE).date().isoformat()
            except (KeyError,ValueError,TypeError):
                continue
            if day in daily:
                attendances.append(attendance)
                daily[day]['ia' if attendance['canal']=='ai' else 'humano']+=1
        ids={a['id'] for a in attendances}
        # Mesmo recorte de dias civis para gráficos, reclamações e métricas.
        classified=[c for c in ComplaintService(self.repository,self.clinic).list() if c['attendance_id'] in ids]
        from services import COMPLAINT_CATEGORIES
        categories=[]
        for key,label in COMPLAINT_CATEGORIES.items():
            entries=[c for c in classified if c['reclamacao'] and c['categoria']==key]
            if entries: categories.append(dict(categoria=key,rotulo=label,total=len(entries),exemplos=[c['motivo'] for c in entries if c['motivo']][:3]))
        categories.sort(key=lambda c:-c['total'])
        count=sum(c['total'] for c in categories)
        for c in categories: c['percentual']=round(100*c['total']/count,1)
        total=len(attendances); ai=sum(a['canal']=='ai' for a in attendances)
        summaries={s['attendance_id']:s for s in self.repository.list('summaries',self.clinic)}
        summarized=sum(a['id'] in summaries and summaries[a['id']]['versao']==attendance_version(a) for a in attendances)
        conversation = conversation_metrics(all_attendances, set(dates))
        ratings = [rating for rating in self.repository.list('answer_ratings', self.clinic)
                   if (stamp := message_stamp(rating)) and stamp.astimezone(LOCAL_ZONE).date() in dates]
        useful = sum(rating['util'] for rating in ratings)
        return dict(periodo_dias=dias,inicio=dates[0].isoformat(),fim=dates[-1].isoformat(),
            metricas=dict(atendimentos_semana=total,total_hoje=sum(daily[dates[-1].isoformat()].values()),
                          canal_ia=ai,canal_humano=total-ai,taxa_automatizacao=round(100*ai/total,1) if total else 0,
                          resolvidos=sum(a['status']=='resolved' for a in attendances),resumos=summarized,
                          tempo_resposta=conversation['tempo_resposta'],
                          amostras_tempo_resposta=conversation['amostras_tempo_resposta'],
                          satisfacao=round(100 * useful / len(ratings), 1) if ratings else None),
            principais_duvidas=conversation['principais_duvidas'], avaliacoes=dict(total=len(ratings), uteis=useful),
            grafico=dict(labels=list(daily),ia=[d['ia'] for d in daily.values()],humano=[d['humano'] for d in daily.values()],
                         topicos=dict(labels=[c['rotulo'] for c in categories],valores=[c['total'] for c in categories])),
            reclamacoes=dict(atendimentos=total,analisados=len(classified),pendentes=total-len(classified),reclamacoes=count,categorias=categories),
            atendimentos=sorted(attendances,key=lambda a:a['criado_em'],reverse=True)[:5])
