import argparse
import getpass
from auth import hash_password
from persistence import create_repository

def main():
    parser = argparse.ArgumentParser(description='Provisionamento local explícito')
    parser.add_argument('command', choices=['create-user'])
    parser.add_argument('--email', required=True)
    parser.add_argument('--nome', required=True)
    parser.add_argument('--role', choices=['admin','owner','customer'], required=True)
    parser.add_argument('--clinic', default='')
    args = parser.parse_args()
    if '@' not in args.email or (args.role != 'admin' and not args.clinic.strip()):
        parser.error('E-mail válido e clínica para owner/customer são obrigatórios')
    password = getpass.getpass('Senha (mínimo 12 caracteres): ')
    if password != getpass.getpass('Confirme: '):
        parser.error('Senhas diferentes')
    create_repository().add_user(dict(email=args.email,nome=args.nome,
        iniciais=''.join(p[0] for p in args.nome.split())[:2].upper(),role=args.role,
        empresa_id=args.clinic.strip(),empresa=args.clinic.strip(),empresa_nome=args.clinic.strip(),
        plano='',password_hash=hash_password(password)))
    print('Usuário criado.')

if __name__ == '__main__':
    main()
