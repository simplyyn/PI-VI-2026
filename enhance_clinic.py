"""Amplia a demonstração local sem chamar LLM nem executar migrações."""
from datetime import datetime, timedelta
from catalog import PROCEDURE_OPTIONS
from services import ClinicRecords, ClinicService, Article, Appointment
from management import LOCAL_ZONE

CATALOG_TITLE='Procedimentos disponíveis e avaliação profissional'
CATALOG_TEXT=('DADOS FICTÍCIOS PARA APRESENTAÇÃO ACADÊMICA. Catálogo de opções da clínica de exemplo: '
              +'; '.join(PROCEDURE_OPTIONS)+'. A escolha do procedimento depende de exame e indicação do dentista. '
              'Relato de dor no dente, sensibilidade, sangramento na gengiva ou inchaço não define diagnóstico nem indica canal ou extração. '
              'O próximo passo é uma consulta de avaliação odontológica; para dor persistente, inchaço ou febre, procurar atendimento odontológico com prioridade. '
              'Dificuldade para respirar ou engolir e sangramento intenso que não para precisam de pronto atendimento imediato. '
              'Preços de avaliação, limpeza e clareamento estão no artigo Preços e procedimentos. Os demais valores não estão cadastrados e dependem de orçamento. '
              'Orientação geral de segurança: https://www.nhs.uk/symptoms/toothache/ . Não há prescrição ou confirmação de tratamento pelo assistente.')

def enhance(repository,clinic,today=None):
    today=today or datetime.now(LOCAL_ZONE).date()
    admin=ClinicRecords(repository,clinic)
    kb=ClinicService(repository,clinic)
    titles={a['titulo'] for a in kb.articles()}
    added_article=0
    if CATALOG_TITLE not in titles:
        kb.save_article(Article(titulo=CATALOG_TITLE,categoria='Procedimentos',conteudo=CATALOG_TEXT))
        added_article=1
    patients={p.get('email'):p for p in admin.list('patients')}
    examples=[('ana@example.test',1,'09:00',PROCEDURE_OPTIONS[0],'confirmado'),
              ('bruno@example.test',1,'10:00',PROCEDURE_OPTIONS[1],'pendente'),
              ('carla@example.test',2,'14:00',PROCEDURE_OPTIONS[7],'confirmado'),
              ('ana@example.test',3,'09:30',PROCEDURE_OPTIONS[3],'pendente')]
    existing=admin.list('appointments')
    created=0
    for email,offset,hour,procedure,status in examples:
        patient=patients.get(email)
        if not patient or patient['status']=='inativo':continue
        # Executar novamente não recria as consultas demonstrativas existentes.
        if any(a['paciente_id']==patient['id'] and a['procedimento']==procedure and a['dentista']=='Dra. Marina (exemplo)' for a in existing):continue
        day=today+timedelta(days=offset)
        while day.weekday()>=5:day+=timedelta(days=1)
        for _ in range(14):
            start=int(hour[:2])*60+int(hour[3:])
            overlap=any(a['data']==day.isoformat() and a['dentista']=='Dra. Marina (exemplo)' and a['status']!='cancelado' and int(a['horario'][:2])*60+int(a['horario'][3:5])<start+30 and int(a['horario'][:2])*60+int(a['horario'][3:5])+a['duracao']>start for a in existing)
            if not overlap:break
            day+=timedelta(days=1)
            while day.weekday()>=5:day+=timedelta(days=1)
        else:continue
        result=admin.save('appointments',Appointment(paciente_id=patient['id'],data=day,horario=hour,duracao=30,procedimento=procedure,dentista='Dra. Marina (exemplo)',status=status))
        existing.append(result);created+=1
    return dict(agendamentos_criados=created,artigos_criados=added_article)

if __name__=='__main__':
    from pathlib import Path
    import sqlite3
    from dotenv import dotenv_values
    from persistence import SQLiteRepository
    if dotenv_values('.env').get('SMARTDENT_DATABASE_URL'):
        raise SystemExit('PostgreSQL configurado: nenhuma alteração executada.')
    path=Path('data/smartdent.sqlite3')
    if not path.is_file():raise SystemExit('Banco local não encontrado')
    folder=Path('data/backups');folder.mkdir(exist_ok=True)
    with sqlite3.connect(path) as source,sqlite3.connect(folder/('antes-melhorias-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')) as target:source.backup(target)
    print(enhance(SQLiteRepository(path),'clinica-teste'))
