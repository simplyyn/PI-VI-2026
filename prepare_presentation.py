"""Refresh an existing local SQLite clinic after a consistent backup; no API calls."""
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from analysis import attendance_version
from knowledge_catalog import articles
from management import LOCAL_ZONE
from persistence import SQLiteRepository
from services import Article

PATIENT_NAMES = {
    'Ana Demonstração': 'Ana Souza',
    'Bruno Demonstração': 'Bruno Almeida',
    'Carla Demonstração': 'Carla Oliveira',
    'Diego Demonstração': 'Diego Santos',
}


def clean(text):
    for old,new in PATIENT_NAMES.items(): text=text.replace(old,new)
    text=re.sub(r'\[(?:DEMO|Mensagem de exemplo|Exemplo de reclamação)\]\s*','',text,flags=re.I)
    text=re.sub(r'\s*\((?:exemplo|demonstração|demo|fictício)\)','',text,flags=re.I)
    text=re.sub(r'^Exemplo:\s*','',text,flags=re.I)
    text=text.replace('Orçamento simulado:','Orçamento:').replace('orçamento simulado','orçamento estimativo')
    return text


def refresh(repository,clinic):
    if not isinstance(repository,SQLiteRepository):
        raise ValueError('Somente SQLite local; integração PostgreSQL requer alinhamento separado.')
    curated=[Article(**item).model_dump() for item in articles()]
    now=datetime.now(LOCAL_ZONE)
    counts=dict(artigos_criados=0,artigos_atualizados=0,registros_ajustados=0,usuarios_exibicao_ajustados=0)
    with repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        owners=[json.loads(raw) for (raw,) in db.execute('SELECT data FROM users')]
        if not any(u.get('role')=='owner' and u.get('empresa_id')==clinic for u in owners):
            raise ValueError('Clínica sem owner cadastrado; nenhuma alteração aplicada.')
        rows={i:(kind,json.loads(raw)) for i,kind,raw in db.execute('SELECT id,kind,data FROM records WHERE clinic=?',(clinic,))}
        title_ids={data['titulo']:i for i,(kind,data) in rows.items() if kind=='kb'}
        for article in curated:
            identifier=title_ids.get(article['titulo'])
            if identifier is None:
                value=dict(article,views=0,atualizado=now.strftime('%d/%m/%Y'))
                db.execute("INSERT INTO records(kind,clinic,data) VALUES ('kb',?,?)",(clinic,json.dumps(value,ensure_ascii=False)))
                counts['artigos_criados']+=1
            else:
                previous=rows[identifier][1]
                value=dict(previous,**article)
                if value!=previous:
                    value['atualizado']=now.strftime('%d/%m/%Y')
                    db.execute('UPDATE records SET data=? WHERE clinic=? AND id=?',(json.dumps(value,ensure_ascii=False),clinic,identifier))
                    counts['artigos_atualizados']+=1
                # Keep subsequent label cleanup from replacing this curated version.
                rows[identifier]=('kb',value)

        quote_ids=set()
        changed_attendances={}
        for identifier,(kind,previous) in rows.items():
            value=json.loads(json.dumps(previous))
            if kind=='patients' and value.get('nome') in PATIENT_NAMES:
                value['nome']=PATIENT_NAMES[value['nome']]
                value['iniciais']=''.join(n[0] for n in value['nome'].split())[:2]
            elif kind=='attendance':
                value['cliente']=clean(value['cliente'])
                value['iniciais']=''.join(n[0] for n in value['cliente'].split())[:2]
                value['preview']=clean(value['preview'])
                for message in value.get('mensagens',[]):
                    if message['texto'].startswith('ORÇAMENTO SIMULADO'):
                        message['texto']=(
                            'Orçamento estimativo para avaliação e limpeza:\n'
                            'Consulta de avaliação: R$ 150,00 a R$ 400,00.\n'
                            'Limpeza dental (profilaxia): R$ 150,00 a R$ 500,00.\n'
                            'Total estimado: R$ 300,00 a R$ 900,00.\n'
                            'Referências regionais pesquisadas; o valor final depende da avaliação e do orçamento da clínica. '
                            'Não há pacote fechado nem confirmação de procedimento ou agendamento nesta mensagem.')
                        quote_ids.add(identifier)
                    else: message['texto']=clean(message['texto'])
                changed_attendances[identifier]=dict(value,id=identifier)
            elif kind=='appointments':
                for field in ('dentista','procedimento'): value[field]=clean(value[field])
            elif kind=='stock': value['nome']=clean(value['nome'])
            elif kind=='complaints': value['motivo']=clean(value.get('motivo',''))
            elif kind=='kb' and value.get('titulo')=='Horários de funcionamento e agendamento':
                value['conteudo']=(
                    'Horários de funcionamento: segunda a sexta-feira das 08h às 18h e sábado das 08h às 12h. '
                    'Fechado aos domingos e feriados. A disponibilidade deve ser verificada na agenda e com a equipe. '
                    'O assistente administrativo pode preparar um agendamento, pedir os dados faltantes e gravar após confirmação do responsável. '
                    'O chat do paciente não garante reserva, encaixe ou atendimento fora do expediente.')
                value['atualizado']=now.strftime('%d/%m/%Y')
            elif kind=='kb' and value.get('titulo')=='Políticas, convênios e pagamento':
                value['conteudo']=(
                    'Cancelamento ou remarcação: solicitar com 24 horas de antecedência. Chegar 10 minutos antes da consulta. '
                    'Formas de pagamento cadastradas: Pix, dinheiro e cartão de débito. Parcelamento não cadastrado; confirmar com a recepção. '
                    'Atendimento particular. Não há convênios ou planos cadastrados como aceitos. '
                    'Valores de procedimentos publicados na base são referências de pesquisa, sujeitos a orçamento. '
                    'Não prometer descontos, multas, reembolso, cobertura de planos ou parcelas sem confirmação da equipe.')
                value['atualizado']=now.strftime('%d/%m/%Y')
            if value!=previous:
                db.execute('UPDATE records SET data=? WHERE clinic=? AND id=?',(json.dumps(value,ensure_ascii=False),clinic,identifier))
                counts['registros_ajustados']+=1

        # Summaries of the revised quotation must not repeat the old fixed amounts.
        for identifier,(kind,previous) in rows.items():
            if kind=='summaries' and previous.get('attendance_id') in quote_ids:
                value=dict(previous,resumo=(
                    'O paciente pediu valores para avaliação e limpeza. Foi registrado um orçamento estimativo '
                    'entre R$ 300,00 e R$ 900,00 para os dois serviços, com valor final sujeito à avaliação e confirmação da clínica. '
                    'A mensagem de orçamento não confirmou procedimentos nem um agendamento.'),
                    modelo='revisao-editorial',gerado_em=now.isoformat(),
                    versao=attendance_version(changed_attendances[previous['attendance_id']]))
                db.execute('UPDATE records SET data=? WHERE clinic=? AND id=?',(json.dumps(value,ensure_ascii=False),clinic,identifier))
                counts['registros_ajustados']+=1
        for identifier,raw in db.execute('SELECT id,data FROM users').fetchall():
            user=json.loads(raw)
            if user.get('empresa_id')==clinic and user.get('empresa') in (clinic,'Clínica teste','Clínica de teste',''):
                user['empresa']='Clínica SmartDent'
                db.execute('UPDATE users SET data=? WHERE id=?',(json.dumps(user,ensure_ascii=False),identifier))
                counts['usuarios_exibicao_ajustados']+=1
    return counts


def main():
    from dotenv import dotenv_values
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clinic',required=True)
    args=parser.parse_args()
    config=dotenv_values('.env')
    if os.getenv('SMARTDENT_DATABASE_URL') or config.get('SMARTDENT_DATABASE_URL'):
        parser.error('PostgreSQL configurado: nenhuma alteração executada.')
    root=Path(__file__).resolve().parent
    source=Path(os.getenv('SMARTDENT_DB_PATH') or config.get('SMARTDENT_DB_PATH') or 'data/smartdent.sqlite3').resolve()
    if not source.is_file() or not source.is_relative_to(root):
        parser.error('Exige um SQLite existente dentro do projeto.')
    backup=root/'data'/'backups'/('presentation-'+datetime.now(LOCAL_ZONE).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    backup.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=rw',uri=True) as db:
        with sqlite3.connect(backup) as target: db.backup(target)
    print('Backup consistente:',backup.relative_to(root))
    print(refresh(SQLiteRepository(source),args.clinic))


if __name__=='__main__': main()
