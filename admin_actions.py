"""Allowlisted owner tools: the model proposes JSON, the server reviews and executes."""
import json
import re
from datetime import datetime,timezone,timedelta
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from services import Patient,Stock,Article,Appointment,Attendance,ClinicRecords,ClinicService
from workflows import record,version,audit,require_workflows,WorkflowConflict,now,deliver
from scheduling import normalized
from management import LOCAL_ZONE


TOOLS={
 'paciente_cadastrar':'dados: nome, telefone, email, status, plano',
 'paciente_atualizar':'alvo: ID ou nome; dados: campos do paciente a alterar',
 'atendimento_atualizar':'alvo: ID ou nome do cliente; dados: status=pending/resolved/escalated ou prioridade=normal/urgente ou revisado=true. Respondido manualmente significa revisado, nunca invente uma resposta.',
 'estoque_cadastrar':'dados: nome, categoria, unidade, quantidade, minimo',
 'estoque_atualizar':'alvo: ID ou nome; dados: nome, categoria, unidade, minimo',
 'estoque_movimentar':'alvo: ID ou nome; dados: delta inteiro positivo para entrada, negativo para saída',
 'conhecimento_cadastrar':'dados: titulo, categoria, conteudo, status booleano',
 'conhecimento_atualizar':'alvo: ID ou titulo; dados: campos do artigo a alterar',
 'preco_definir':'alvo: nome exato de um procedimento do catálogo; dados: centavos inteiro, unidade texto, anterior_centavos opcional quando o usuário informar um preço antigo',
 'consulta_atualizar':'alvo: ID da consulta ou nome do paciente (somente se uma consulta); dados: data YYYY-MM-DD, horario HH:MM, duracao inteiro, dentista, procedimento ou status=confirmado/pendente/cancelado',
 'mensagem_enviar':'alvo: ID da conversa ou nome do cliente; dados: texto da mensagem fornecida explicitamente pelo usuário',
 'registro_excluir':'alvo: ID ou nome; dados: tipo=paciente/estoque/conhecimento/consulta. Exige confirmação específica de exclusão.',
}


class ToolPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    ferramenta:Literal[tuple(TOOLS)]
    alvo:str|int|None=None
    dados:dict=Field(default_factory=dict)


def resolve(repo,clinic,kind,target):
    rows=ClinicRecords(repo,clinic).list(kind) if kind in ('patients','appointments','attendance') else repo.list(kind,clinic)
    if isinstance(target,int) or str(target).isdigit(): matches=[r for r in rows if r['id']==int(target)]
    else:
        label={'patients':'nome','attendance':'cliente','appointments':'paciente','stock':'nome','kb':'titulo'}[kind]
        matches=[r for r in rows if normalized(str(target or '')) in normalized(r[label])]
    if len(matches)!=1:
        options='; '.join(f"{r['id']}: {r.get('nome',r.get('cliente',r.get('paciente',r.get('titulo','registro'))))}"+(f" — {r['data']} {r['horario'][:5]}, {r['dentista']}, {r['status']}" if kind=='appointments' else '') for r in matches[:8])
        raise WorkflowConflict('Registro não encontrado na sua clínica.' if not matches else 'Há mais de um registro. Informe o ID: '+options)
    return matches[0]


class AdminActions:
    def __init__(self,repo,user):
        require_workflows(repo)
        if user.get('role')!='owner':raise WorkflowConflict('Somente o responsável da clínica pode executar ferramentas administrativas.')
        self.repo,self.user,self.clinic=repo,user,user['empresa_id']

    def interpret(self,text,llm):
        from catalog import PROCEDURE_OPTIONS
        # No patient history, knowledge articles, SQL, credentials or arbitrary endpoints enter the planner.
        output=llm.generate([
            {'role':'system','content':'Interprete apenas o pedido explícito do administrador. Retorne SOMENTE JSON {"ferramenta":...,"alvo":...,"dados":{...}}. Não invente dados faltantes nem escreva mensagens sem texto fornecido pelo administrador. Não execute nada. Se não houver parâmetros suficientes, retorne {"erro":"pergunta objetiva"}. Valores monetários em centavos inteiros. Ferramentas permitidas: '+json.dumps(TOOLS,ensure_ascii=False)+' Catálogo de procedimentos: '+json.dumps(PROCEDURE_OPTIONS,ensure_ascii=False)+'. Hoje em America/Sao_Paulo: '+datetime.now(LOCAL_ZONE).date().isoformat()},
            {'role':'user','content':text}])
        if not isinstance(output,str):raise WorkflowConflict('O modelo não retornou um plano válido. Reformule o pedido.')
        output=output.strip()
        if output.startswith('```'):output=re.sub(r'^```(?:json)?\s*|\s*```$','',output)
        if len(output)>12000: raise WorkflowConflict('Pedido muito grande. Divida em alterações menores.')
        try: value=json.loads(output)
        except (ValueError,TypeError): raise WorkflowConflict('Não consegui estruturar o pedido. Informe registro, campo e novo valor.') from None
        if isinstance(value,dict) and isinstance(value.get('erro'),str):raise WorkflowConflict(value['erro'][:400])
        try: plan=ToolPlan.model_validate(value)
        except ValueError:raise WorkflowConflict('O plano da IA não corresponde a uma operação permitida. Reformule o pedido.') from None
        return self.prepare(plan)

    def materialize(self,plan):
        tool,args,target=plan.ferramenta,plan.dados,plan.alvo
        specs={'paciente':('patients',Patient),'estoque':('stock',Stock),'conhecimento':('kb',Article),'consulta':('appointments',Appointment),'atendimento':('attendance',Attendance)}
        if tool=='preco_definir':
            from catalog import PROCEDURE_OPTIONS
            matches=[p for p in PROCEDURE_OPTIONS if normalized(str(target or '')) in normalized(p)]
            name=matches[0] if len(matches)==1 else next((p for p in PROCEDURE_OPTIONS if normalized(p)==normalized(str(target))),None)
            if not name:raise WorkflowConflict('Informe um procedimento exato do catálogo: '+', '.join(PROCEDURE_OPTIONS))
            if set(args)-{'centavos','unidade','anterior_centavos'}:raise ValueError('Campo inválido')
            cents=args.get('centavos');unit=args.get('unidade','por procedimento')
            if type(cents) is not int or not 0<cents<=100000000 or not isinstance(unit,str) or not 1<=len(unit)<=100:raise WorkflowConflict('Informe valor positivo e unidade de cobrança.')
            current=next((p for p in self.repo.list('prices',self.clinic) if p['procedimento']==name),None)
            if 'anterior_centavos' in args and (current is None or args['anterior_centavos']!=current['centavos']):
                raise WorkflowConflict('O preço próprio anterior não corresponde ao informado. Referências de mercado não são preço da clínica. Consulte os preços ou peça explicitamente para definir um novo preço.')
            return dict(kind='prices',id=current['id'] if current else None,before=current,after=dict(procedimento=name,centavos=cents,unidade=unit,status=True),label=name)
        if tool=='mensagem_enviar':
            item=resolve(self.repo,self.clinic,'attendance',target)
            if set(args)!={'texto'} or not isinstance(args['texto'],str) or not 1<=len(args['texto'].strip())<=4000:raise WorkflowConflict('Informe o texto exato da mensagem para revisar antes do envio.')
            return dict(kind='message',id=item['id'],before=item,after=args,label=item['cliente'])
        if tool=='registro_excluir':
            if set(args)!={'tipo'} or args['tipo'] not in specs:raise WorkflowConflict('Informe o tipo e o ID do registro a excluir.')
            kind,_=specs[args['tipo']];item=resolve(self.repo,self.clinic,kind,target)
            return dict(kind=kind,id=item['id'],before=item,after=None,label='Excluir registro '+str(item['id']))
        prefix,mode=tool.rsplit('_',1);kind,model=specs[prefix]
        item=resolve(self.repo,self.clinic,kind,target) if mode!='cadastrar' else None
        if tool=='estoque_movimentar':
            if set(args)!={'delta'} or type(args['delta']) is not int or not args['delta']:raise WorkflowConflict('Informe a quantidade inteira de entrada ou saída.')
            if not 0<=item['quantidade']+args['delta']<=1000000000:raise WorkflowConflict('Saldo de estoque inválido.')
            return dict(kind='move',id=item['id'],before=item,after=args,label=item['nome'])
        if tool=='atendimento_atualizar':
            if set(args)-{'status','prioridade','revisado'} or not args:raise WorkflowConflict('Use status, prioridade ou revisão manual.')
            if 'status' in args and args['status'] not in ('pending','resolved','escalated'):raise ValueError('Status inválido')
            if 'prioridade' in args and args['prioridade'] not in ('normal','urgente'):raise ValueError('Prioridade inválida')
            if 'revisado' in args and type(args['revisado']) is not bool:raise ValueError('Revisão inválida')
            meta=next((m for m in self.repo.list('attendance_meta',self.clinic) if m['attendance_id']==item['id']),None)
            return dict(kind='attendance_meta',id=item['id'],before=dict(attendance=item,metadata=meta),after=args,label=item['cliente'])
        if mode=='atualizar' and not args:raise WorkflowConflict('Informe os campos e novos valores.')
        if set(args)-set(model.model_fields):raise WorkflowConflict('Há campos que não pertencem a esse cadastro.')
        if prefix=='estoque' and mode=='atualizar' and 'quantidade' in args:raise WorkflowConflict('Para alterar o saldo use uma movimentação de estoque.')
        base={key:item[key] for key in model.model_fields if item and key in item}
        if kind=='appointments' and 'dentista' in args and 'profissional_id' not in args:base.pop('profissional_id',None)
        try: after=model.model_validate(dict(base,**args)).model_dump(mode='json')
        except ValueError as exc:raise WorkflowConflict('Dados incompletos ou inválidos: '+', '.join(str(e['loc'][-1]) for e in exc.errors())) from None
        if kind=='appointments':
            self._validate_appointment(after,item['id'] if item else None)
        label=(item or after).get('nome',(item or after).get('titulo',str(target or 'novo registro')))
        if kind=='appointments':label=item['paciente']+' — '+item['data']+' '+item['horario'][:5]
        return dict(kind=kind,id=item['id'] if item else None,before=item,after=after,label=label)

    def _validate_appointment(self,data,identifier):
        from professionals import validate_professional
        from scheduling import check_conflict
        if data.get('profissional_id') is None:data.pop('profissional_id',None)
        from management import LOCAL_ZONE
        if data['status']!='cancelado' and datetime.fromisoformat(data['data']+'T'+data['horario']).replace(tzinfo=LOCAL_ZONE)<=datetime.now(LOCAL_ZONE):
            raise WorkflowConflict('Para remarcar, informe uma data futura.')
        validate_professional(self.repo.list('professionals',self.clinic),data)
        check_conflict(self.repo.list('appointments',self.clinic),data,identifier)

    def prepare(self,plan):
        proposal=self.materialize(plan)
        draft=self.repo.save('action_drafts',self.clinic,dict(user_id=self.user['id'],created_at=now(),plan=plan.model_dump(),proposal=proposal))
        before=proposal['before'] or {}
        after=proposal['after']
        if proposal['kind']=='message': summary='Mensagem: '+after['texto']
        elif proposal['kind']=='prices': summary=f"Preço próprio: {('R$ '+format(before['centavos']/100,'.2f')) if before else 'não cadastrado'} → R$ {after['centavos']/100:.2f}, {after['unidade']}. Não altera as referências de mercado."
        elif after is None: summary='Exclusão permanente. Verifique as dependências e o registro.'
        else: summary='; '.join(f"{k}: {before.get(k,'não cadastrado')} → {v}" for k,v in after.items() if before.get(k)!=v)
        confirmation=f"EXCLUIR {proposal['id']}" if after is None else 'confirmar'
        return dict(id=draft['id'],resposta=f"Revise {proposal['label']} (ID {proposal['id'] or 'novo'}): {summary}\nNada foi alterado. Digite “{confirmation}” para executar ou “cancelar”.",origem='operacao',gerado_por_llm=False,fontes=[],acoes=[])

    def confirm(self,identifier,text):
        with self.repo.transaction() as tx:
            draft=record(tx,'action_drafts',self.clinic,identifier)
            if draft['user_id']!=self.user['id']:raise LookupError('Operação não encontrada')
            receipt=next((r for r in tx.list('action_receipts',self.clinic) if r['draft_id']==identifier and r['user_id']==self.user['id']),None)
            if receipt:return self.result('Essa operação já foi processada. Não foi executada novamente.')
            if datetime.now(timezone.utc)-datetime.fromisoformat(draft['created_at'])>timedelta(minutes=30):raise WorkflowConflict('Operação expirada. Faça um novo pedido.')
            proposal=draft['proposal'];expected=f"EXCLUIR {proposal['id']}" if proposal['after'] is None else 'confirmar'
            if text.strip().casefold()!=expected.casefold():raise WorkflowConflict('Para executar esta operação digite exatamente: '+expected)
            worker=AdminActions(tx,self.user);current=worker.materialize(ToolPlan.model_validate(draft['plan']))
            if version(current)!=version(proposal):raise WorkflowConflict('O registro mudou desde a prévia. Faça um novo pedido para revisar os valores atuais.')
            kind,data,pid=current['kind'],current['after'],current['id']
            if data is None:
                if kind in ('patients','appointments'):ClinicRecords(tx,self.clinic).delete(kind,pid)
                else:tx.delete(kind,self.clinic,pid)
            elif kind=='prices':pid=tx.save('prices',self.clinic,data,pid)['id']
            elif kind=='move':ClinicService(tx,self.clinic).move(pid,data['delta'])
            elif kind=='message':deliver(tx,self.user,pid,data['texto'],f'action:{identifier}',expected=version(current['before']))
            elif kind=='attendance_meta':
                item=current['before']['attendance'];meta=current['before']['metadata']
                if 'status' in data:
                    item.pop('id');item['status']=data['status'];tx.save('attendance',self.clinic,item,pid)
                value=dict(meta or {},attendance_id=pid)
                value.pop('id',None)
                if 'prioridade' in data:value['prioridade']=data['prioridade']
                if 'revisado' in data:value['revisado']=data['revisado'];value['revisado_em']=now()
                tx.save('attendance_meta',self.clinic,value,meta['id'] if meta else None)
            elif kind=='kb':pid=ClinicService(tx,self.clinic).save_article(Article(**data),pid)['id']
            elif kind=='stock':pid=ClinicService(tx,self.clinic).save_stock(Stock(**data),pid)['id']
            else:pid=ClinicRecords(tx,self.clinic).save(kind,{'patients':Patient,'appointments':Appointment}[kind](**data),pid)['id']
            tx.save('action_receipts',self.clinic,dict(draft_id=identifier,user_id=self.user['id'],created_at=now()))
            audit(tx,self.user,draft['plan']['ferramenta'],pid or 'novo',tuple(data or {}))
        reply=self.result('Operação concluída e registrada no banco. A revisão manual de uma conversa não equivale a enviar uma resposta.' if kind=='attendance_meta' else 'Operação concluída e registrada no banco.')
        path={'patients':'/pacientes','appointments':'/agendamentos','stock':'/estoque','move':'/estoque','kb':'/base-conhecimento','prices':'/base-conhecimento','attendance_meta':'/atendimentos','message':'/atendimentos'}.get(kind,'/atendimentos')
        if kind=='appointments' and pid and data is not None:
            reply.update(registro_tipo=kind,registro_id=pid,acoes=[dict(rotulo='Ver no calendário',url=f'/agendamentos?agendamento_id={pid}')])
            return reply
        reply.update(registro_tipo=kind,registro_id=pid,acoes=[dict(rotulo='Conferir resultado',url=path)])
        return reply

    @staticmethod
    def result(text):return dict(resposta=text,origem='operacao',gerado_por_llm=False,fontes=[],acoes=[])
