"""SQLite provisório; substitua este adaptador após alinhamento com Guilherme."""
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

class SQLiteRepository:
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
        with self.connect() as db:
            cursor = db.execute('INSERT INTO users(email,data) VALUES (?,?)', (data['email'], json.dumps(data)))
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
    return SQLiteRepository(os.getenv('SMARTDENT_DB_PATH', 'data/smartdent.sqlite3'))
