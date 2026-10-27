"""RF004/RF006: resumos persistidos e indicadores calculados, sem dados demonstrativos."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from analysis import attendance_version
from services import ClinicRecords, ComplaintService

try:
    LOCAL_ZONE = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:
    LOCAL_ZONE = timezone(timedelta(hours=-3))

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
        for attendance in self.repository.list('attendance',self.clinic):
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
        return dict(periodo_dias=dias,inicio=dates[0].isoformat(),fim=dates[-1].isoformat(),
            metricas=dict(atendimentos_semana=total,total_hoje=sum(daily[dates[-1].isoformat()].values()),
                          canal_ia=ai,canal_humano=total-ai,taxa_automatizacao=round(100*ai/total,1) if total else 0,
                          resolvidos=sum(a['status']=='resolved' for a in attendances),resumos=summarized,
                          tempo_resposta=None,satisfacao=None),
            grafico=dict(labels=list(daily),ia=[d['ia'] for d in daily.values()],humano=[d['humano'] for d in daily.values()],
                         topicos=dict(labels=[c['rotulo'] for c in categories],valores=[c['total'] for c in categories])),
            reclamacoes=dict(atendimentos=total,analisados=len(classified),pendentes=total-len(classified),reclamacoes=count,categorias=categories),
            atendimentos=sorted(attendances,key=lambda a:a['criado_em'],reverse=True)[:5])
