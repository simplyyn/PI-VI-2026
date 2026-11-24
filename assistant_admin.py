"""Owner routing for operational reports, batch previews and confirmed tools."""
import re
from collections import Counter
from datetime import datetime,timedelta
from assistant import normalize,result
from management import LOCAL_ZONE
from workflows import pending,BatchReplies,WorkflowConflict,require_workflows
from admin_actions import AdminActions
from services import ClinicRecords


def named_professional(repo,clinic,m):
    """Profissional ativo citado pelo nome na mensagem (qualquer cadastro, não só nomes fixos)."""
    return next((p for p in repo.list('professionals',clinic)
                 if p['ativo'] and re.search(r'\b'+re.escape(normalize(p['nome']))+r'\b',m)),None)


def calendar_link(rows=(),professional=None,day=None):
    """Link que abre a agenda já filtrada e destaca a consulta (ou o dia) pedida."""
    if rows:
        url=f"/agendamentos?agendamento_id={rows[0]['id']}"
        if professional:url+=f"&profissional_id={professional['id']}"
        return ('Ver no calendário',url)
    params=[f"profissional_id={professional['id']}"] if professional else []
    if day:params.append(f"data={day.isoformat()}")
    return ('Ver no calendário','/agendamentos'+('?'+'&'.join(params) if params else ''))


def respond(request,user,text,llm_factory,generator):
    repo=request.app.state.repository;clinic=user['empresa_id'];m=normalize(text)
    if not getattr(repo,'supports_workflows',False):return None
    if request.session.get('reply_batch') and m in ('confirmar','confirmo','sim'):
        return result('Revise e confirme as mensagens selecionadas na tela do lote. Nenhuma resposta foi enviada por esta mensagem.',('Revisar lote',f"/respostas?lote={request.session['reply_batch']}"))
    if request.session.get('admin_action'):
        if m=='cancelar':
            request.session.pop('admin_action',None)
            return result('Operação descartada. Nenhum registro foi alterado.')
        from scheduling import EASY_CONFIRM_WORDS,confirmation_text
        easy=confirmation_text(m) in EASY_CONFIRM_WORDS
        if easy or m.startswith('excluir '):
            try:answer=AdminActions(repo,user).confirm(request.session['admin_action'],'confirmar' if easy else text)
            except (WorkflowConflict,ValueError,LookupError) as error:return result(str(error))
            # Keep its receipt reachable so repeating a confirmation is harmless.
            return answer
    if ('respost' in m or 'respon' in m) and any(s in m for s in ('todos','todas','lote','prepare respostas')):
        draft=BatchReplies(repo,user).prepare(generator)
        request.session.pop('admin_action',None);request.session.pop('admin_followup',None);request.session.pop('booking',None)
        request.session['reply_batch']=draft['id']
        return result(f"Preparei uma prévia para {len(draft['items'])} conversa(s). Nenhuma mensagem foi enviada. Abra a revisão, edite e confirme as selecionadas.",('Revisar respostas',f"/respostas?lote={draft['id']}"))
    if any(s in m for s in ('sem resposta','sem responder','nao respondi','aguardando resposta','mais tempo','mensagens pendentes')):
        p=pending(repo,clinic);lines=[f"• {r['cliente']}: {r['mensagens_pendentes']} mensagem(ns), aguardando desde {datetime.fromisoformat(r['desde']).astimezone(LOCAL_ZONE).strftime('%d/%m %H:%M')}." for r in p['itens'][:10]]
        actions=[('Revisar pendências','/respostas')]+[(f"Abrir {r['cliente']}",f"/atendimentos?atendimento_id={r['id']}") for r in p['itens'][:5]]
        return result(f"Há {p['conversas']} conversa(s), {p['pacientes_identificados']} paciente(s) identificado(s) e {p['mensagens']} mensagem(ns) aguardando resposta. {p['conversas_sem_vinculo']} conversa(s) sem vínculo cadastral não entram na contagem de pacientes únicos.\n"+'\n'.join(lines)+'\nSugestões não enviadas e revisões manuais não encerram a espera.',*actions)
    if any(s in m for s in ('profissionais','especialidades','dentistas','quem faz cirurgia')):
        profiles=[p for p in repo.list('professionals',clinic) if p['ativo']]
        return result('\n'.join(f"{p['nome']}: {', '.join(p['especialidades'])}. Procedimentos: {', '.join(p['procedimentos'])}." for p in profiles) or 'Nenhum profissional cadastrado.',
                      ('Abrir agenda','/agendamentos'),*[(f"Agenda de {p['nome']}",f"/agendamentos?profissional_id={p['id']}") for p in profiles[:6]])
    if ('horario' in m or 'disponib' in m) and named_professional(repo,clinic,m):
        from professionals import available
        p=named_professional(repo,clinic,m)
        day=datetime.now(LOCAL_ZONE).date()+timedelta(days=2 if 'depois de amanha' in m else int('amanha' in m))
        explicit=re.search(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b',m)
        if explicit:
            try:day=datetime.strptime(explicit.group(1),'%d/%m/%Y' if '/' in explicit.group(1) else '%Y-%m-%d').date()
            except ValueError:return result('Informe uma data válida.')
        slots=available(repo,clinic,p['id'],day.isoformat(),p['duracao_padrao'])
        return result(f"{p['nome']}, {day.strftime('%d/%m/%Y')}, duração de referência {p['duracao_padrao']} minutos: "+(', '.join(slots) if slots else 'nenhum horário livre cadastrado.')+' Para reservar, peça o agendamento e confirme os dados; a disponibilidade será verificada novamente.',calendar_link(professional=p,day=day))
    if any(s in m for s in ('precos da clinica','precos cadastrados','tabela da clinica')):
        values=repo.list('prices',clinic)
        return result('\n'.join(f"{p['procedimento']}: R$ {p['centavos']/100:.2f} ({p['unidade']})." for p in values if p['status']) or 'Não há preços próprios da clínica cadastrados. A base contém referências de pesquisa; você pode pedir para definir um preço próprio.')
    doctor=named_professional(repo,clinic,m)
    from booking_input import BOOKING_INTENT
    doctor_agenda=(doctor and re.search(r'\b(?:agenda|consultas|agendamentos|pacientes)\b',m)
                   and not BOOKING_INTENT.search(m)
                   and not re.search(r'\b(?:altere|atualize|troque|mude|exclua|remova|remarque|cancele|marque|cadastre|registre)\b',m))
    if doctor_agenda or any(s in m for s in ('mais agendad','por profissional','consultas canceladas','agendamentos cancelados')):
        rows=ClinicRecords(repo,clinic).list('appointments')
        today=datetime.now(LOCAL_ZONE).date();start=today;end=today+timedelta(days=6)
        last=re.search(r'ultimos?\s+(\d+)\s+dias?',m)
        if last:
            days=int(last.group(1))
            if not 1<=days<=365:return result('Informe um período de 1 a 365 dias para esse relatório.')
            start=today-timedelta(days=days-1);end=today
        if 'amanha' in m:start=end=today+timedelta(days=1)
        elif 'hoje' in m:start=end=today
        rows=[r for r in rows if start.isoformat()<=r['data']<=end.isoformat()]
        if 'cancelad' in m:rows=[r for r in rows if r['status']=='cancelado']
        else: rows=[r for r in rows if r['status']!='cancelado']
        if doctor:rows=[r for r in rows if r.get('profissional_id')==doctor['id'] or normalize(r['dentista'])==normalize(doctor['nome'])]
        rows.sort(key=lambda r:(r['data'],r['horario']))
        if 'mais agendad' in m:
            body='\n'.join(f"{k}: {v}" for k,v in Counter(r['procedimento'] for r in rows).most_common(10))
        elif 'por profissional' in m:
            body='\n'.join(f"{k}: {v}" for k,v in Counter(r['dentista'] for r in rows).items())
        else:body='\n'.join(f"{r['data']} {r['horario'][:5]} — {r['paciente']}, {r['dentista']}, {r['status']}" for r in rows[:15])
        return result(f"Período: {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}. {len(rows)} consulta(s) registrada(s)"+(f" para {doctor['nome']}" if doctor else '')+".\n"+(body or 'Nenhum registro no período.'),
                      calendar_link(rows if 'cancelad' not in m else (),doctor,start))
    if ('prioridade' in m or 'urgentes' in m) and not re.search(r'\b(marque|altere|troque|defina|mude|atualize)\b',m):
        metas=repo.list('attendance_meta',clinic);labels={r['id']:r['cliente'] for r in repo.list('attendance',clinic)}
        urgent=[r for r in metas if r.get('prioridade')=='urgente']
        return result(f"{len(urgent)} atendimento(s) com prioridade administrativa urgente:\n"+'\n'.join(labels.get(r['attendance_id'],'Atendimento removido') for r in urgent)+'\nPrioridade administrativa não substitui avaliação clínica.',('Abrir atendimentos','/atendimentos'))
    mutation=re.search(r'\b(altere|alterar|atualize|atualizar|troque|mude|aumente|defina|cadastre|cadastrar|registre|registre|adicione|exclua|excluir|remova|remarque|remarcar|cancele|marque.*urgente|marque.*respondid|envie|enviar)\b',m)
    if mutation or request.session.get('admin_followup'):
        if not mutation and any(w in m for w in ('quantos','quais','relatorio','agenda de','estoque baixo','horarios')):return None
        command=text if mutation else request.session['admin_followup']+'\nComplemento do administrador: '+text
        try: draft=AdminActions(repo,user).interpret(command,llm_factory())
        except (WorkflowConflict,ValueError,LookupError) as error:
            request.session['admin_followup']=command[-1500:]
            return result(str(error))
        request.session.pop('admin_followup',None);request.session.pop('booking',None)
        request.session.pop('reply_batch',None)
        request.session['admin_action']=draft['id']
        return draft
    return None
