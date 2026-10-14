"""Contrato do repositório e adaptador SQLite provisório (fallback de desenvolvimento).

O adaptador definitivo é postgres.PostgresRepository, usado quando SMARTDENT_DATABASE_URL está definido.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

class Repository(Protocol):
    def user(self, email): ...
    def user_by_id(self, user_id): ...
    def add_user(self, data): ...
    def list(self, kind, clinic): ...
    def save(self, kind, clinic, data, identifier=None): ...
    def delete(self, kind, clinic, identifier): ...
    def move(self, clinic, identifier, delta): ...
    def append_message(self, clinic, identifier, message): ...
    def set_complaint(self, clinic, attendance_id, data): ...
    def delete_complaint(self, clinic, attendance_id): ...

class SQLiteRepository:
    supports_semantic_search = False

    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,clinic TEXT NOT NULL,data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS records_scope ON records(kind,clinic);''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def user(self, email):
        with self.connect() as db:
            row = db.execute('SELECT id,data FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        return dict(json.loads(row[1]), id=row[0]) if row else None

    def user_by_id(self, user_id):
        with self.connect() as db:
            row = db.execute('SELECT id,data FROM users WHERE id=?', (user_id,)).fetchone()
        return dict(json.loads(row[1]), id=row[0]) if row else None

    def add_user(self, data):
        data = dict(data, email=data['email'].strip().lower())
        try:
            with self.connect() as db:
                cursor = db.execute('INSERT INTO users(email,data) VALUES (?,?)', (data['email'], json.dumps(data)))
        except sqlite3.IntegrityError:
            raise ValueError('E-mail já cadastrado') from None
        return dict(data, id=cursor.lastrowid)

    def list(self, kind, clinic):
        with self.connect() as db:
            rows = db.execute('SELECT id,data FROM records WHERE kind=? AND clinic=? ORDER BY id', (kind, clinic)).fetchall()
        return [dict(json.loads(data), id=identifier) for identifier, data in rows]

    def save(self, kind, clinic, data, identifier=None):
        with self.connect() as db:
            if identifier is None:
                identifier = db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)', (kind,clinic,json.dumps(data))).lastrowid
            else:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT data FROM records WHERE id=? AND kind=? AND clinic=?',(identifier,kind,clinic)).fetchone()
                if not row:
                    raise LookupError('Registro não encontrado')
                if kind == 'attendance':
                    data = dict(data,mensagens=json.loads(row[0]).get('mensagens',[]))
                db.execute('UPDATE records SET data=? WHERE id=? AND kind=? AND clinic=?', (json.dumps(data),identifier,kind,clinic))
        return dict(data, id=identifier)

    def delete(self, kind, clinic, identifier):
        with self.connect() as db:
            if not db.execute('DELETE FROM records WHERE id=? AND kind=? AND clinic=?', (identifier,kind,clinic)).rowcount:
                raise LookupError('Registro não encontrado')
            if kind == 'attendance':
                db.execute("DELETE FROM records WHERE kind='complaints' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,identifier))

    def set_complaint(self, clinic, attendance_id, data):
        data = dict(data, attendance_id=attendance_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM records WHERE id=? AND kind=? AND clinic=?',(attendance_id,'attendance',clinic)).fetchone():
                raise LookupError('Registro não encontrado')
            row = db.execute("SELECT id FROM records WHERE kind='complaints' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,attendance_id)).fetchone()
            if row:
                identifier = row[0]
                db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),identifier))
            else:
                identifier = db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)',('complaints',clinic,json.dumps(data))).lastrowid
        return dict(data,id=identifier)

    def delete_complaint(self, clinic, attendance_id):
        with self.connect() as db:
            if not db.execute("DELETE FROM records WHERE kind='complaints' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,attendance_id)).rowcount:
                raise LookupError('Registro não encontrado')

    def append_message(self, clinic, identifier, message):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM records WHERE id=? AND kind=? AND clinic=?',(identifier,'attendance',clinic)).fetchone()
            if not row:
                raise LookupError('Registro não encontrado')
            data = json.loads(row[0])
            data.setdefault('mensagens',[]).append(message)
            db.execute('UPDATE records SET data=? WHERE id=? AND kind=? AND clinic=?',(json.dumps(data),identifier,'attendance',clinic))
        return dict(data,id=identifier)

    def move(self, clinic, identifier, delta):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM records WHERE id=? AND kind=? AND clinic=?', (identifier,'stock',clinic)).fetchone()
            if not row:
                raise LookupError('Registro não encontrado')
            data = json.loads(row[0])
            quantity = data['quantidade'] + delta
            if quantity < 0 or quantity > 1000000000:
                raise ValueError('Saldo inválido')
            data['quantidade'] = quantity
            db.execute('UPDATE records SET data=? WHERE id=? AND kind=? AND clinic=?', (json.dumps(data),identifier,'stock',clinic))
        return dict(data, id=identifier)

def create_repository() -> Repository:
    url = os.getenv('SMARTDENT_DATABASE_URL')
    if url:
        from embeddings import create_embedder
        from postgres import PostgresRepository
        return PostgresRepository(url, embedder=create_embedder(),
                                  max_distance=float(os.getenv('SMARTDENT_RETRIEVAL_MAX_DISTANCE', '0.7')),
                                  pool_size=int(os.getenv('SMARTDENT_DB_POOL_SIZE', '10')))
    if os.getenv('SMARTDENT_ENV') == 'production':
        raise RuntimeError('Configure SMARTDENT_DATABASE_URL (PostgreSQL) em produção; SQLite é só para desenvolvimento')
    return SQLiteRepository(os.getenv('SMARTDENT_DB_PATH', 'data/smartdent.sqlite3'))
