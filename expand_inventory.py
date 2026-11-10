"""Add presentation stock without replacing existing balances; consistent backup in CLI."""
import argparse,json,os,sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import dotenv_values
from persistence import SQLiteRepository
from services import Stock,ClinicService
from scheduling import normalized
from management import LOCAL_ZONE
from workflows import require_workflows,audit

MATERIALS=[
 ('Gaze estéril','Descartáveis','Pacote',0,8),
 ('Babadores descartáveis','Descartáveis','Pacote',5,10),
 ('Toucas descartáveis','EPI','Pacote',10,4),
 ('Aventais descartáveis','EPI','Pacote',2,5),
 ('Fio dental','Prevenção','Unidade',12,5),
 ('Soro fisiológico','Materiais clínicos','Frasco',8,4),
 ('Solução antisséptica','Materiais clínicos','Frasco',2,3),
 ('Lâminas de bisturi','Cirurgia','Caixa',6,3),
 ('Fios de sutura','Cirurgia','Caixa',4,4),
 ('Agulhas descartáveis','Materiais clínicos','Caixa',2,3),
 ('Anestésico odontológico','Materiais clínicos','Caixa',6,3),
 ('Cimento de ionômero de vidro','Restauração','Kit',3,2),
 ('Ácido condicionador','Restauração','Seringa',6,3),
 ('Adesivo odontológico','Restauração','Frasco',2,2),
 ('Microaplicadores','Restauração','Pacote',5,4),
 ('Brocas odontológicas','Instrumental','Unidade',12,6),
 ('Discos de acabamento','Restauração','Unidade',8,4),
 ('Papel grau cirúrgico','Esterilização','Rolo',1,3),
 ('Indicadores químicos de esterilização','Esterilização','Caixa',0,2),
 ('Pontas sugadoras cirúrgicas','Cirurgia','Pacote',3,2),
]


def expand(repo,clinic):
 require_workflows(repo)
 added=0
 with repo.transaction() as tx:
  with tx.connect() as db:users=[dict(json.loads(raw),id=i) for i,raw in db.execute('SELECT id,data FROM users')]
  owner=next((u for u in users if u.get('role')=='owner' and u.get('empresa_id')==clinic),None)
  if not owner:raise ValueError('Clínica sem responsável cadastrado.')
  service=ClinicService(tx,clinic);names={normalized(s['nome']) for s in service.stocks()}
  for name,category,unit,quantity,minimum in MATERIALS:
   if normalized(name) in names:continue
   item=service.save_stock(Stock(nome=name,categoria=category,unidade=unit,quantidade=quantity,minimo=minimum))
   audit(tx,owner,'presentation_stock_created',item['id'],('nome','categoria','unidade','quantidade','minimo'))
   names.add(normalized(name));added+=1
 return dict(itens_adicionados=added,total_itens=len(ClinicService(repo,clinic).stocks()))


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--clinic',required=True);args=parser.parse_args();config=dotenv_values('.env')
 if os.getenv('SMARTDENT_DATABASE_URL') or config.get('SMARTDENT_DATABASE_URL'):parser.error('PostgreSQL configurado: nenhuma alteração aplicada.')
 root=Path(__file__).resolve().parent;path=Path(os.getenv('SMARTDENT_DB_PATH') or config.get('SMARTDENT_DB_PATH') or 'data/smartdent.sqlite3').resolve()
 if not path.is_file() or not path.is_relative_to(root):parser.error('Exige SQLite existente dentro do projeto.')
 backup=root/'data/backups'/('inventory-'+datetime.now(LOCAL_ZONE).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3');backup.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(path.as_uri()+'?mode=rw',uri=True) as source:
  with sqlite3.connect(backup) as target:source.backup(target)
 print('Backup:',backup.relative_to(root));print(expand(SQLiteRepository(path),args.clinic))

if __name__=='__main__':main()
