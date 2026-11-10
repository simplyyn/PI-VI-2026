"""Provision local presentation professionals and a linked patient login after backup."""
import argparse
import json
import os
import secrets
import sqlite3
from datetime import datetime,timedelta
from pathlib import Path
from dotenv import dotenv_values
from auth import hash_password
from persistence import SQLiteRepository
from services import ClinicRecords,Appointment
from management import LOCAL_ZONE
from professionals import Professional,available


def prepare(repo,clinic,patient_id,email):
    from workflows import audit,WorkflowConflict
    if not getattr(repo,'supports_workflows',False):raise ValueError('Somente SQLite local nesta entrega.')
    weekdays={str(i):[['08:00','12:00'],['13:00','18:00']] for i in range(5)}
    weekdays['5']=[['08:00','12:00']]
    profiles=[Professional(nome='Elias',especialidades=['Avaliação cirúrgica','Cirurgia oral','Reabilitação'],procedimentos=['Avaliação cirúrgica','Consulta de avaliação','Extração dentária simples','Extração de siso','Implante dentário','Tratamento de canal','Coroa dentária'],expediente=weekdays,duracao_padrao=60),
              Professional(nome='Roberto',especialidades=['Prevenção','Clínica geral'],procedimentos=['Consulta de avaliação','Limpeza dental (profilaxia)','Restauração dentária','Clareamento dental','Aplicação tópica de flúor','Aplicação de selante'],expediente=weekdays,duracao_padrao=30)]
    password=None
    with repo.transaction() as tx:
        with tx.connect() as db:
            owners=[dict(json.loads(raw),id=i) for i,raw in db.execute('SELECT id,data FROM users')]
        owner=next((u for u in owners if u.get('role')=='owner' and u.get('empresa_id')==clinic),None)
        if not owner:raise ValueError('Clínica sem owner cadastrado.')
        patient=ClinicRecords(tx,clinic).get('patients',patient_id)
        if patient['status']=='inativo':raise ValueError('Escolha um paciente ativo.')
        saved=[]
        for profile in profiles:
            existing=next((p for p in tx.list('professionals',clinic) if p['nome']==profile.nome),None)
            saved.append(tx.save('professionals',clinic,profile.model_dump(),existing['id'] if existing else None))
        user=tx.user(email)
        if user and (user['role']!='customer' or user['empresa_id']!=clinic):raise WorkflowConflict('E-mail pertence a outro perfil/clínica. Nenhum acesso foi alterado.')
        if not user:
            password=secrets.token_urlsafe(18)
            user=tx.add_user(dict(email=email,nome=patient['nome'],iniciais=patient['iniciais'],role='customer',empresa_id=clinic,empresa='Clínica SmartDent',empresa_nome='Clínica SmartDent',password_hash=hash_password(password)))
        links=[r for r in tx.list('customer_links',clinic) if r['user_id']==user['id']]
        if links and links[0]['patient_id']!=patient_id:raise WorkflowConflict('Esse usuário já está vinculado a outro paciente.')
        if not links:tx.save('customer_links',clinic,dict(user_id=user['id'],patient_id=patient_id))
        ClinicRecords(tx,clinic).patient_attendance(patient_id)
        today=datetime.now(LOCAL_ZONE).date()
        for profile in saved:
            procedure='Avaliação cirúrgica' if profile['nome']=='Elias' else 'Limpeza dental (profilaxia)'
            existing=[a for a in tx.list('appointments',clinic) if a.get('profissional_id')==profile['id'] and a['paciente_id']==patient_id and a['data']>=today.isoformat() and a['status']!='cancelado']
            if existing:continue
            for offset in range(1,8):
                day=(today+timedelta(days=offset)).isoformat()
                slots=available(tx,clinic,profile['id'],day,profile['duracao_padrao'])
                for hour in slots:
                    try:ClinicRecords(tx,clinic).save('appointments',Appointment(paciente_id=patient_id,profissional_id=profile['id'],data=day,horario=hour,duracao=profile['duracao_padrao'],procedimento=procedure,dentista=profile['nome'],status='confirmado'))
                    except ValueError:continue
                    break
                else:continue
                break
        audit(tx,owner,'prepare_presentation_access',patient_id,('professionals','customer_link','appointments'))
    return dict(email=email,password=password,patient_id=patient_id,user_id=user['id'],professionals=[p['id'] for p in saved])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clinic',required=True);parser.add_argument('--patient-id',type=int,required=True);parser.add_argument('--email',required=True)
    args=parser.parse_args();config=dotenv_values('.env')
    if os.getenv('SMARTDENT_DATABASE_URL') or config.get('SMARTDENT_DATABASE_URL'):parser.error('PostgreSQL configurado. Nenhuma alteração aplicada.')
    root=Path(__file__).resolve().parent;source=Path(os.getenv('SMARTDENT_DB_PATH') or config.get('SMARTDENT_DB_PATH') or 'data/smartdent.sqlite3').resolve()
    if not source.is_file() or not source.is_relative_to(root):parser.error('SQLite existente dentro do projeto é obrigatório.')
    backup=root/'data'/'backups'/('integrated-'+datetime.now(LOCAL_ZONE).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3');backup.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=rw',uri=True) as db:
        with sqlite3.connect(backup) as dest:db.backup(dest)
    result=prepare(SQLiteRepository(source),args.clinic,args.patient_id,args.email)
    access=root/'data'/'acesso-cliente.txt'
    if result['password']:
        access.write_text('Acesso privado do paciente — não publicar\nURL: http://127.0.0.1:8000/chat\nE-mail: '+result['email']+'\nSenha: '+result['password']+'\n',encoding='utf-8')
    print('Backup:',backup.relative_to(root));print('Profissionais preparados e acesso vinculado ao paciente ID',result['patient_id'])
    print('Credencial nova salva em data/acesso-cliente.txt.' if result['password'] else 'Usuário existente preservado; nenhuma senha foi alterada.')


if __name__=='__main__':main()
