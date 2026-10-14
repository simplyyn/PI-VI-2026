import argparse
import getpass
import os
from auth import hash_password
from persistence import create_repository

def create_user(parser, args):
    if '@' not in args.email or (args.role != 'admin' and not args.clinic.strip()):
        parser.error('E-mail válido e clínica para owner/customer são obrigatórios')
    password = getpass.getpass('Senha (mínimo 12 caracteres): ')
    if password != getpass.getpass('Confirme: '):
        parser.error('Senhas diferentes')
    clinic = args.clinic.strip()
    repository = create_repository()
    try:
        repository.add_user(dict(email=args.email,nome=args.nome,
            iniciais=''.join(p[0] for p in args.nome.split())[:2].upper(),role=args.role,
            empresa_id=clinic,empresa=clinic,empresa_nome=(args.clinic_nome or clinic).strip(),
            plano='',password_hash=hash_password(password)))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        if hasattr(repository,'close'):
            repository.close()
    print('Usuário criado.')

def database_url(parser):
    url = os.getenv('SMARTDENT_DATABASE_URL')
    if not url:
        parser.error('Defina SMARTDENT_DATABASE_URL com a URL do PostgreSQL')
    return url

def migrate(parser, args):
    from postgres import migrate as apply
    applied = apply(database_url(parser))
    print('Migrações aplicadas: ' + (', '.join(applied) if applied else 'nenhuma (esquema atualizado).'))

def reindex(parser, args):
    from embeddings import create_embedder
    from postgres import PostgresRepository
    embedder = create_embedder()
    if embedder is None:
        parser.error('SMARTDENT_EMBEDDINGS=off: habilite os embeddings para reindexar')
    repository = PostgresRepository(database_url(parser), embedder=embedder)
    try:
        print(f'Artigos indexados: {repository.reindex(force=args.todos)}')
    finally:
        repository.close()

def main():
    parser = argparse.ArgumentParser(description='Provisionamento e manutenção local explícitos')
    commands = parser.add_subparsers(dest='command', required=True)
    user = commands.add_parser('create-user', help='Cria usuário (senha solicitada no terminal)')
    user.add_argument('--email', required=True)
    user.add_argument('--nome', required=True)
    user.add_argument('--role', choices=['admin','owner','customer'], required=True)
    user.add_argument('--clinic', default='', help='Identificador da clínica (ex.: clinica-teste)')
    user.add_argument('--clinic-nome', default='', help='Nome exibido da clínica, ao criá-la no PostgreSQL')
    user.set_defaults(handler=create_user)
    commands.add_parser('migrate', help='Aplica migrações pendentes no PostgreSQL').set_defaults(handler=migrate)
    index = commands.add_parser('reindex', help='Gera embeddings dos artigos sem índice semântico')
    index.add_argument('--todos', action='store_true', help='Reindexa todos os artigos (ex.: após trocar o modelo)')
    index.set_defaults(handler=reindex)
    args = parser.parse_args()
    args.handler(parser, args)

if __name__ == '__main__':
    main()
