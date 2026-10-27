"""Atualização local autorizada: vínculos existentes, rótulos e orçamento simulado."""
from datetime import datetime, timezone
from decimal import Decimal
import re
from services import ClinicRecords, Attendance

def prepare(repository,clinic):
    service=ClinicRecords(repository,clinic)
    patients=service.list('patients')
    original=service.list('attendance')
    linked=[]
    for patient in patients:
        matches=[a for a in original if a['cliente'].strip().casefold()==patient['nome'].strip().casefold()]
        same_name=[p for p in patients if p['nome'].strip().casefold()==patient['nome'].strip().casefold()]
        candidate=matches[0]['id'] if len(matches)==1 and len(same_name)==1 else None
        linked.append(service.patient_attendance(patient['id'],candidate)['id'])
    renamed=0
    for kind,field in [('stock','nome'),('kb','titulo')]:
        for record in repository.list(kind,clinic):
            if record[field].startswith('[DEMO] '):
                identifier=record.pop('id')
                record[field]=record[field].removeprefix('[DEMO] ')
                repository.save(kind,clinic,record,identifier)
                renamed+=1
    patient=next((p for p in patients if p.get('email')=='ana@example.test'),None)
    quote_id=None
    if patient:
        article=next((a for a in repository.list('kb',clinic) if a['titulo']=='Preços e procedimentos'),None)
        if not article: raise ValueError('Artigo de preços não encontrado para a simulação')
        prices=[]
        for pattern in [r'consulta de avaliação R\$\s*([\d.,]+)',r'limpeza dental \(profilaxia\) R\$\s*([\d.,]+)']:
            match=re.search(pattern,article['conteudo'],re.I)
            if not match: raise ValueError('Preço não identificado; simulação não gerada')
            prices.append(Decimal(match[1].replace('.','').replace(',','.')))
        conversation=service.patient_attendance(patient['id'])
        quote_id=conversation['id']
        if not any(m['texto'].startswith('ORÇAMENTO SIMULADO') for m in conversation.get('mensagens',[])):
            data=Attendance(cliente=patient['nome'],preview='Orçamento simulado: avaliação e limpeza',status='pending',canal='human')
            service.save('attendance',data,quote_id)
            now=datetime.now(timezone.utc).isoformat()
            repository.append_message(clinic,quote_id,dict(texto='Olá! Gostaria de um orçamento para uma consulta de avaliação e uma limpeza dental.',autor='client',criado_em=now))
            money=lambda value:f'R$ {value:.2f}'.replace('.',',')
            text=f'ORÇAMENTO SIMULADO — valores fictícios para apresentação.\n1 consulta de avaliação: {money(prices[0])}\n1 limpeza dental (profilaxia): {money(prices[1])}\nTotal estimado: {money(sum(prices))}.\nFonte: artigo [{article["id"]}] {article["titulo"]}. Valores sujeitos à confirmação e avaliação profissional. Nenhum procedimento ou agendamento foi confirmado.'
            repository.append_message(clinic,quote_id,dict(texto=text,autor='human',criado_em=now))
    return dict(pacientes_vinculados=len(linked),rotulos_atualizados=renamed,orcamento_atendimento_id=quote_id)

if __name__=='__main__':
    import sqlite3
    from pathlib import Path
    from dotenv import dotenv_values
    from persistence import SQLiteRepository
    if dotenv_values('.env').get('SMARTDENT_DATABASE_URL'):
        raise SystemExit('PostgreSQL configurado: nenhum banco alterado. Autorize e aplique a migração antes.')
    path=Path('data/smartdent.sqlite3')
    backup=Path('data/backups')
    backup.mkdir(exist_ok=True)
    with sqlite3.connect(path) as source,sqlite3.connect(backup/('antes-integracao-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')) as target:
        source.backup(target)
    print(prepare(SQLiteRepository(path),'clinica-teste'))
