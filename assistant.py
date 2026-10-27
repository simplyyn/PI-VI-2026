"""Consultas operacionais fundamentadas nos registros da clínica, sem executar escritas."""
import re
import unicodedata
from datetime import datetime, timedelta
from management import LOCAL_ZONE, ManagementReport
from services import ClinicRecords, ClinicService
from analysis import attendance_version

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c)).strip(' \t\r\n!?.,')

def result(text, *actions):
    return dict(resposta=text,origem='registros',gerado_por_llm=False,fontes=[],
                acoes=[dict(rotulo=label,url=url) for label,url in actions])

class ClinicAssistant:
    def __init__(self,repository,clinic):
        self.repository,self.clinic=repository,clinic
        self.records=ClinicRecords(repository,clinic)

    def reply(self,question,context=None):
        m=normalize(question)
        if re.fullmatch(r'(e )?(hoje|amanha|na semana|na proxima semana|os ativos|os novos|os esgotados|os baixos)',m):
            valid=(context=='agenda' and any(t in m for t in ('hoje','amanha','semana'))) or (context=='pacientes' and any(t in m for t in ('ativos','novos'))) or (context=='estoque' and any(t in m for t in ('esgotados','baixos')))
            prefix={'agenda':'agendamentos','pacientes':'pacientes','estoque':'estoque'}.get(context) if valid else None
            if prefix:m=prefix+' '+m
            else:return result('Você quer consultar a agenda, os pacientes ou o estoque? Escolha um atalho ou escreva, por exemplo, "agenda de amanhã".',('Abrir agenda','/agendamentos'))
        if m in ('oi','ola','bom dia','boa tarde','boa noite','ajuda') or any(p in m for p in ('o que voce pode','como pode me ajudar','suas funcionalidades')):
            return result('Olá! Posso consultar sua agenda, localizar pacientes, mostrar o estoque, acompanhar reclamações e resumir os indicadores da clínica. Também respondo sobre preços, procedimentos, horários e políticas cadastrados. Para registrar ou alterar dados, abro a tela certa para você conferir.',('Ver agenda','/agendamentos'),('Ver atendimentos','/atendimentos'))
        if m in ('obrigado','obrigada','valeu','ok','entendi','perfeito'):
            return result('Por nada! Quando precisar, escolha um dos atalhos ou me diga o que quer consultar na clínica.')
        if re.search(r'\b(agende|marque|cadastre|exclua|remova|altere|adicione|registre|cancele)\b',m):
            url='/agendamentos' if re.search(r'agend|consulta',m) else '/estoque' if 'estoque' in m else '/pacientes' if 'paciente' in m else '/atendimentos'
            return result('Posso te levar ao formulário para conferir e salvar os dados. Não fiz nenhuma alteração nem confirmei agendamentos nesta conversa.',('Abrir formulário',url))
        if re.search(r'\b(agenda|agendamentos)\b',m) or any(p in m for p in ('proximas consultas','consultas de hoje','consultas de amanha','consultas para amanha','consultas da semana','consultas hoje','consultas amanha')):
            return self.agenda(m)
        if 'estoque' in m or any(p in m for p in ('repor','reposicao','insumos','esgotados')):
            stocks=ClinicService(self.repository,self.clinic).stocks()
            if 'esgotad' in m: stocks=[s for s in stocks if s['quantidade']==0]
            elif any(p in m for p in ('baixo','repor','reposicao','faltando')): stocks=[s for s in stocks if s['quantidade']<s['minimo'] or s['quantidade']==0]
            if not stocks:return result('Não encontrei itens nessa condição. Você pode conferir o cadastro completo na tela de estoque.',('Conferir estoque','/estoque'))
            lines=[f"• {s['nome']}: {s['quantidade']} {s['unidade']} (mínimo {s['minimo']})." for s in stocks[:8]]
            return result(f'Encontrei {len(stocks)} item(ns) para a sua consulta:\n'+'\n'.join(lines)+('\nMostrei os primeiros 8; abra o estoque para ver todos.' if len(stocks)>8 else ''),('Abrir estoque','/estoque'))
        if any(p in m for p in ('quantos pacientes','listar pacientes','pacientes cadastrados','pacientes ativos','pacientes novos','novos pacientes','buscar paciente','localizar paciente')) or re.search(r'\b(mostre|liste|listar|ver|quais|meus) (os )?pacientes\b',m) or (context=='pacientes' and m.startswith('pacientes ')):
            if re.search(r'\b(dor|dores|diagnostico|doenca|sintoma|sintomas)\b',m):
                return result('Não há um prontuário clínico estruturado para filtrar pacientes por sintomas ou diagnóstico. Posso consultar nomes e status cadastrais; confira as conversas individualmente com a equipe.',('Abrir pacientes','/pacientes'),('Ver atendimentos','/atendimentos'))
            patients=self.records.list('patients')
            if 'ativos' in m: patients=[p for p in patients if p['status']=='ativo']
            if 'novos' in m: patients=[p for p in patients if p['status']=='novo']
            for prefix in ('buscar paciente','localizar paciente'):
                if prefix in m:
                    name=m.split(prefix,1)[1].strip(' :?')
                    if name:patients=[p for p in patients if name in normalize(p['nome'])]
            names='\n'.join(f"• {p['nome']} — {p['status']}." for p in patients[:8])
            return result(f'Encontrei {len(patients)} paciente(s) nessa consulta.'+ ('\n'+names if names else ' Nenhum registro corresponde ao filtro.')+('\nMostrei os primeiros 8.' if len(patients)>8 else ''),('Abrir pacientes','/pacientes'))
        if 'reclam' in m:
            report=ManagementReport(self.repository,self.clinic).build(7)['reclamacoes']
            lines=[f"• {c['rotulo']}: {c['total']}." for c in report['categorias']]
            return result(f"Nos atendimentos cadastrados nos últimos 7 dias, há {report['reclamacoes']} reclamação(ões) identificada(s).\n"+'\n'.join(lines)+f"\n{report['analisados']} atendimento(s) analisado(s) e {report['pendentes']} ainda sem classificação. Relato de dor não é, por si só, reclamação sobre a clínica.",('Ver relatórios','/relatorios'),('Analisar atendimentos','/atendimentos'))
        if 'resumo' in m and any(p in m for p in ('pendente','atualizad','atendimentos')):
            attendances=self.records.list('attendance')
            summaries={s['attendance_id']:s for s in self.repository.list('summaries',self.clinic)}
            ready=sum(a['id'] in summaries and summaries[a['id']]['versao']==attendance_version(a) for a in attendances)
            return result(f"Dos {len(attendances)} atendimentos cadastrados, {ready} têm resumo atualizado e {len(attendances)-ready} precisam gerar ou atualizar o resumo. Abra a conversa e use Resumo da IA; isso não confirma tratamento nem consulta.",('Abrir atendimentos','/atendimentos'))
        if 'atendimento' in m and any(p in m for p in ('pendente','resolvid','escalad','hoje','quantos','listar')):
            if 'hoje' in m:
                total=ManagementReport(self.repository,self.clinic).build(7)['metricas']['total_hoje']
                return result(f'Hoje foram cadastrados {total} atendimentos/conversas na clínica. Esse número inclui conversas criadas para pacientes e não representa consultas realizadas.',('Ver atendimentos','/atendimentos'))
            attendances=self.records.list('attendance')
            status=next((value for word,value in [('pendente','pending'),('resolvid','resolved'),('escalad','escalated')] if word in m),None)
            if status:attendances=[a for a in attendances if a['status']==status]
            lines=[f"• {a['cliente']}: {a['preview']}" for a in attendances[:6]]
            return result(f'Encontrei {len(attendances)} atendimento(s) nessa consulta.\n'+'\n'.join(lines)+('\nMostrei os primeiros 6; abra Atendimentos para consultar todos.' if len(attendances)>6 else ''),('Abrir atendimentos','/atendimentos'))
        if any(p in m for p in ('resumo da semana','relatorio','indicador','balanco da semana')):
            r=ManagementReport(self.repository,self.clinic).build(7)
            v=r['metricas']
            return result(f"Aqui está o panorama dos últimos 7 dias:\n• {v['atendimentos_semana']} atendimentos cadastrados; {v['resolvidos']} marcados como resolvidos.\n• {v['resumos']} resumos atualizados.\n• {r['reclamacoes']['reclamacoes']} reclamações identificadas; {r['reclamacoes']['pendentes']} atendimentos ainda não analisados.\nOs números vêm dos registros da sua clínica. Não há medição de satisfação ou de tempo de resposta.",('Detalhar relatórios','/relatorios'))
        return None

    def agenda(self,question):
        today=datetime.now(LOCAL_ZONE).date()
        if 'amanha' in question:start=end=today+timedelta(days=1);label='amanhã'
        elif 'hoje' in question:start=end=today;label='hoje'
        else:start=today;end=today+timedelta(days=6);label='os próximos 7 dias'
        appointments=[a for a in self.records.list('appointments') if a['status']!='cancelado' and start.isoformat()<=a['data']<=end.isoformat()]
        appointments.sort(key=lambda a:(a['data'],a['horario']))
        if not appointments:return result(f'Não há consultas não canceladas cadastradas para {label}. Posso te levar à agenda para conferir outras datas ou cadastrar uma consulta.',('Abrir agenda','/agendamentos'))
        lines=[f"• {a['data'][8:10]}/{a['data'][5:7]}, {a['horario'][:5]} — {a['paciente']}: {a['procedimento']} ({a['status']})." for a in appointments[:8]]
        return result(f'Para {label}, encontrei {len(appointments)} consulta(s):\n'+'\n'.join(lines)+('\nMostrei as primeiras 8.' if len(appointments)>8 else '')+'\nSão os agendamentos registrados; nenhum horário foi criado ou alterado por mim.',('Abrir agenda','/agendamentos'))
