"""Mensagens fictícias para testar conversas e reclamações, sem chamar serviços externos."""
from datetime import datetime,timezone
from services import ClinicRecords,ComplaintService,ComplaintVerdict

EXAMPLE_COMPLAINT='[Exemplo de reclamação] Na minha última visita, esperei cerca de 50 minutos sem receber aviso sobre o atraso. Fiquei insatisfeito com a falta de informação e gostaria que a recepção me mantivesse atualizado.'
EXAMPLES={
    'Ana Demonstração':'[Mensagem de exemplo] Olá! Gostaria de saber os valores da avaliação e da limpeza antes de decidir um horário.',
    'Bruno Demonstração':EXAMPLE_COMPLAINT,
    'Carla Demonstração':'[Mensagem de exemplo] Olá! Quero entender como funciona a avaliação ortodôntica e quais horários a clínica oferece.',
    'Diego Demonstração':'[Mensagem de exemplo] Boa tarde! Quais são os horários de funcionamento e a política para remarcar uma consulta?',
}

def populate(repository,clinic):
    service=ClinicRecords(repository,clinic)
    counts=dict(mensagens_adicionadas=0,reclamacoes_classificadas=0)
    for attendance in service.list('attendance'):
        message=EXAMPLES.get(attendance['cliente'],'[Mensagem de exemplo] Olá! Gostaria de receber informações sobre a consulta de avaliação e os horários da clínica.')
        messages=attendance.get('mensagens',[])
        complaint_case=attendance['cliente']=='Bruno Demonstração'
        needs_message=not any(m['autor']=='client' for m in messages)
        if complaint_case:needs_message=not any(m['texto']==EXAMPLE_COMPLAINT for m in messages)
        if needs_message:
            repository.append_message(clinic,attendance['id'],dict(texto=message,autor='client',criado_em=datetime.now(timezone.utc).isoformat()))
            counts['mensagens_adicionadas']+=1
        if complaint_case:
            existing=ComplaintService(repository,clinic).list()
            if not any(c['attendance_id']==attendance['id'] for c in existing):
                ComplaintService(repository,clinic).set_manual(attendance['id'],ComplaintVerdict(reclamacao=True,categoria='tempo_espera',motivo='Exemplo: insatisfação com espera de 50 minutos e falta de aviso sobre o atraso.'))
                counts['reclamacoes_classificadas']+=1
    return counts

if __name__=='__main__':
    from pathlib import Path
    import sqlite3
    from dotenv import dotenv_values
    from persistence import SQLiteRepository
    if dotenv_values('.env').get('SMARTDENT_DATABASE_URL'):
        raise SystemExit('PostgreSQL configurado: nenhum dado alterado.')
    path=Path('data/smartdent.sqlite3')
    if not path.is_file():raise SystemExit('Banco local não encontrado')
    folder=Path('data/backups');folder.mkdir(exist_ok=True)
    with sqlite3.connect(path) as source,sqlite3.connect(folder/('antes-mensagens-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')) as target:source.backup(target)
    print(populate(SQLiteRepository(path),'clinica-teste'))
