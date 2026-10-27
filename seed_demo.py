"""Dados fictícios e idempotentes para demonstração local. Nunca importa pacientes reais."""
import argparse
from services import ClinicRecords, ClinicService, Patient, Stock, Article
from persistence import SQLiteRepository

PATIENTS = [
    dict(nome='Ana Demonstração',telefone='(00) 00000-0001',email='ana@example.test',status='ativo',plano='Particular'),
    dict(nome='Bruno Demonstração',telefone='(00) 00000-0002',email='bruno@example.test',status='novo',plano='Particular'),
    dict(nome='Carla Demonstração',telefone='(00) 00000-0003',email='carla@example.test',status='ativo',plano='Particular'),
    dict(nome='Diego Demonstração',telefone='(00) 00000-0004',email='diego@example.test',status='inativo',plano='Particular'),
]
STOCK = [
    dict(nome='Luvas de procedimento',categoria='EPI',unidade='Caixa',quantidade=12,minimo=5),
    dict(nome='Máscaras descartáveis',categoria='EPI',unidade='Caixa',quantidade=3,minimo=5),
    dict(nome='Resina composta',categoria='Restauração',unidade='Seringa',quantidade=8,minimo=3),
    dict(nome='Sugadores descartáveis',categoria='Instrumental',unidade='Pacote',quantidade=0,minimo=2),
    dict(nome='Alginato',categoria='Moldagem',unidade='Pote',quantidade=6,minimo=2),
]
ARTICLES = [
    dict(titulo='Preços e procedimentos',categoria='Financeiro',conteudo='DADOS FICTÍCIOS PARA APRESENTAÇÃO ACADÊMICA. Não representam preços reais nem orientação clínica. Tabela de preços e valores da clínica fictícia: consulta de avaliação R$ 120,00; limpeza dental (profilaxia) R$ 180,00; clareamento dental R$ 650,00. Os valores são demonstrativos. Outros procedimentos precisam de avaliação e não possuem preço cadastrado. Não confirmar indicação clínica ou orçamento de procedimento não cadastrado.'),
    dict(titulo='Horários de funcionamento e agendamento',categoria='Agendamento',conteudo='DADOS FICTÍCIOS PARA APRESENTAÇÃO ACADÊMICA. Horários de funcionamento e atendimento: segunda a sexta-feira das 08h às 18h; sábado das 08h às 12h. Fechado aos domingos e feriados. Funcionamento não significa disponibilidade de agenda. Para agendar consulta, solicitar confirmação à recepção; o assistente não reserva horários nem garante encaixes.'),
    dict(titulo='Políticas, convênios e pagamento',categoria='Políticas',conteudo='DADOS FICTÍCIOS PARA APRESENTAÇÃO ACADÊMICA. Políticas da clínica fictícia: cancelamento ou remarcação de consulta deve ser solicitado com 24 horas de antecedência. Chegar 10 minutos antes do horário. Pagamento demonstrativo por Pix, dinheiro ou cartão de débito; não há parcelamento cadastrado. Atendimento particular; nenhum convênio ou plano odontológico está cadastrado como aceito. Não inventar planos, descontos ou multas. Dúvidas e situações não previstas devem ser confirmadas com a recepção.'),
]

def seed(repository,clinic):
    admin=ClinicRecords(repository,clinic)
    service=ClinicService(repository,clinic)
    counts={'pacientes':0,'estoque':0,'artigos':0}
    emails={p.get('email') for p in admin.list('patients')}
    for data in PATIENTS:
        if data['email'] not in emails:
            admin.save('patients',Patient(**data));counts['pacientes']+=1
    names={i['nome'].removeprefix('[DEMO] ') for i in service.stocks()}
    for data in STOCK:
        if data['nome'] not in names:
            service.save_stock(Stock(**data));counts['estoque']+=1
    titles={a['titulo'].removeprefix('[DEMO] ') for a in service.articles()}
    for data in ARTICLES:
        if data['titulo'] not in titles:
            service.save_article(Article(**data));counts['artigos']+=1
    return counts

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clinic',required=True)
    parser.add_argument('--db',default='data/smartdent.sqlite3')
    args=parser.parse_args()
    from pathlib import Path
    if not Path(args.db).is_file(): parser.error('Banco SQLite existente não encontrado')
    repo=SQLiteRepository(args.db)
    import json
    with repo.connect() as db:
        owners=[json.loads(row[0]) for row in db.execute('SELECT data FROM users')]
    if not any(u.get('empresa_id')==args.clinic and u.get('role')=='owner' for u in owners):
        parser.error('A clínica precisa ter um owner cadastrado nesse banco')
    print(seed(repo,args.clinic))
