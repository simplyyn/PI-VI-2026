"""Reassociate legacy presentation appointments without changing their clinical history."""
import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values
from persistence import SQLiteRepository
from management import LOCAL_ZONE
from scheduling import normalized,check_conflict
from professionals import validate_professional
from workflows import require_workflows,audit,WorkflowConflict,now


def repair(repo,clinic):
    require_workflows(repo)
    with repo.transaction() as tx:
        with tx.connect() as db:
            users=[dict(json.loads(raw),id=i) for i,raw in db.execute('SELECT id,data FROM users')]
        owner=next((u for u in users if u.get('role')=='owner' and u.get('empresa_id')==clinic),None)
        if not owner:raise WorkflowConflict('Clínica sem responsável cadastrado.')
        profiles=tx.list('professionals',clinic)
        if {p['nome'] for p in profiles}!={'Elias','Roberto'} or len(profiles)!=2:
            raise WorkflowConflict('A preparação exige exatamente os cadastros Elias e Roberto; nenhum outro cadastro será removido.')
        by_name={p['nome']:p for p in profiles}
        rows=tx.list('appointments',clinic);changes=[]
        today=datetime.now(LOCAL_ZONE).date().isoformat()
        for row in rows:
            if row.get('profissional_id') in {p['id'] for p in profiles} and row['dentista'] in by_name:continue
            procedure=normalized(row['procedimento'])
            if any(word in procedure for word in ('cirurg','canal','siso','implante','coroa','ortodont')):target=by_name['Elias']
            elif any(word in procedure for word in ('limpeza','profilaxia','restaur','avaliacao','consulta','clareamento','fluor','selante')):target=by_name['Roberto']
            else:raise WorkflowConflict('Consulta #'+str(row['id'])+' precisa de revisão manual do profissional. Nada foi alterado.')
            changes.append((row,dict(row,dentista=target['nome'],profissional_id=target['id'])))
        proposed={a['id']:a for a in rows}
        proposed.update({new['id']:new for _,new in changes})
        for old,new in changes:
            if new['data']>=today and new['status']!='cancelado':
                validate_professional(profiles,new)
                check_conflict(list(proposed.values()),new,new['id'])
            # Historical records keep date, time, procedure and status. This is not a new clinical appointment.
            tx.save('appointment_reassignments',clinic,dict(appointment_id=old['id'],profissional_anterior=old['dentista'],profissional_id_anterior=old.get('profissional_id'),novo_profissional_id=new['profissional_id'],motivo='Padronização administrativa dos registros da apresentação',created_at=now()))
            with tx.connect() as db:
                payload={k:v for k,v in new.items() if k!='id'}
                db.execute("UPDATE records SET data=? WHERE clinic=? AND kind='appointments' AND id=?",(json.dumps(payload,ensure_ascii=False),clinic,new['id']))
            audit(tx,owner,'presentation_professional_reassignment',old['id'],('profissional_id','dentista'))
    return dict(consultas_reassociadas=len(changes),profissionais=len(profiles))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--clinic',required=True);args=parser.parse_args()
    config=dotenv_values('.env')
    if os.getenv('SMARTDENT_DATABASE_URL') or config.get('SMARTDENT_DATABASE_URL'):parser.error('PostgreSQL configurado. Nenhuma alteração aplicada.')
    root=Path(__file__).resolve().parent;path=Path(os.getenv('SMARTDENT_DB_PATH') or config.get('SMARTDENT_DB_PATH') or 'data/smartdent.sqlite3').resolve()
    if not path.is_file() or not path.is_relative_to(root):parser.error('Exige SQLite existente dentro do projeto.')
    backup=root/'data'/'backups'/('professionals-'+datetime.now(LOCAL_ZONE).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3');backup.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path.as_uri()+'?mode=rw',uri=True) as source:
        with sqlite3.connect(backup) as dest:source.backup(dest)
    print('Backup consistente:',backup.relative_to(root));print(repair(SQLiteRepository(path),args.clinic))


if __name__=='__main__':main()
