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
    def set_summary(self, clinic, attendance_id, data): ...
    def ensure_patient_attendance(self, clinic, patient_id, data, existing_id=None): ...
    def save_appointment(self, clinic, data, identifier=None, operation_key=None): ...

class SQLiteRepository:
    supports_semantic_search = False
    supports_booking_receipts = True
    supports_workflows = True

    @contextmanager
    def transaction(self):
        """A unit of work reuses this connection; inner services cannot commit early."""
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            child=object.__new__(SQLiteRepository)
            child.path=self.path
            @contextmanager
            def same_connection():
                yield db
            child.connect=same_connection
            yield child

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

    def clinic_owner(self, clinic):
        with self.connect() as db:
            row = db.execute("SELECT id, data FROM users WHERE json_extract(data, '$.empresa_id')=? "
                             "AND json_extract(data, '$.role')='owner' ORDER BY id LIMIT 1", (clinic,)).fetchone()
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
        if kind == 'appointments':
            return self.save_appointment(clinic,data,identifier)
        with self.connect() as db:
            if identifier is None:
                identifier = db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)', (kind,clinic,json.dumps(data))).lastrowid
            else:
                if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT data FROM records WHERE id=? AND kind=? AND clinic=?',(identifier,kind,clinic)).fetchone()
                if not row:
                    raise LookupError('Registro não encontrado')
                if kind == 'attendance':
                    data = dict(data,mensagens=json.loads(row[0]).get('mensagens',[]))
                db.execute('UPDATE records SET data=? WHERE id=? AND kind=? AND clinic=?', (json.dumps(data),identifier,kind,clinic))
        return dict(data, id=identifier)

    def save_appointment(self, clinic, data, identifier=None, operation_key=None):
        from scheduling import check_conflict
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            if operation_key:
                receipt=db.execute("SELECT data FROM records WHERE kind='booking_receipts' AND clinic=? AND json_extract(data,'$.key')=?",(clinic,operation_key)).fetchone()
                if receipt:
                    saved_id=json.loads(receipt[0])['appointment_id']
                    row=db.execute("SELECT data FROM records WHERE kind='appointments' AND clinic=? AND id=?",(clinic,saved_id)).fetchone()
                    if not row:
                        raise ValueError('Confirmação já processada; o agendamento foi removido. Inicie um novo pedido.')
                    return dict(json.loads(row[0]),id=saved_id)
            patient=db.execute("SELECT data FROM records WHERE kind='patients' AND clinic=? AND id=?",(clinic,data['paciente_id'])).fetchone()
            if not patient:
                raise LookupError('Paciente não encontrado')
            if operation_key and json.loads(patient[0]).get('status')=='inativo':
                raise ValueError('Paciente inativo')
            rows=db.execute("SELECT id,data FROM records WHERE kind='appointments' AND clinic=?",(clinic,)).fetchall()
            appointments=[dict(json.loads(raw),id=i) for i,raw in rows]
            from professionals import validate_professional
            professionals=[dict(json.loads(raw),id=i) for i,raw in db.execute("SELECT id,data FROM records WHERE kind='professionals' AND clinic=?",(clinic,)).fetchall()]
            existing = next((appointment for appointment in appointments if appointment['id'] == identifier), None)
            if identifier is not None and existing is None:
                raise LookupError('Registro não encontrado')
            if existing and existing.get('realizado_em'):
                raise ValueError('Desfaça a marcação de realizado antes de editar a consulta.')
            data=validate_professional(professionals,data)
            check_conflict(appointments,data,identifier)
            if identifier is None:
                identifier=db.execute("INSERT INTO records(kind,clinic,data) VALUES ('appointments',?,?)",(clinic,json.dumps(data))).lastrowid
            else:
                db.execute("UPDATE records SET data=? WHERE kind='appointments' AND clinic=? AND id=?",(json.dumps(data),clinic,identifier))
            if operation_key:
                db.execute("INSERT INTO records(kind,clinic,data) VALUES ('booking_receipts',?,?)",(clinic,json.dumps(dict(key=operation_key,appointment_id=identifier))))
        return dict(data,id=identifier)

    def set_appointment_completion(self, clinic, identifier, completed, now):
        from datetime import datetime, timedelta
        from scheduling import AppointmentConflict

        with self.connect() as db:
            if not db.in_transaction:
                db.execute('BEGIN IMMEDIATE')
            row = db.execute(
                "SELECT data FROM records WHERE clinic=? AND kind='appointments' AND id=?", (clinic, identifier)
            ).fetchone()
            if row is None:
                raise LookupError('Agendamento não encontrado')
            appointment = json.loads(row[0])
            if completed and not appointment.get('realizado_em'):
                end = datetime.fromisoformat(f"{appointment['data']}T{appointment['horario']}").replace(tzinfo=now.tzinfo)
                end += timedelta(minutes=appointment['duracao'])
                if appointment['status'] == 'cancelado' or end > now:
                    raise AppointmentConflict('Só é possível marcar como realizada uma consulta não cancelada após seu horário.')
                appointment['realizado_em'] = appointment['data']
            elif not completed:
                appointment.pop('realizado_em', None)
            db.execute("UPDATE records SET data=? WHERE clinic=? AND kind='appointments' AND id=?",
                       (json.dumps(appointment), clinic, identifier))
            return dict(appointment, id=identifier)

    def sync_professional_name(self,clinic,professional_id):
        with self.connect() as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data FROM records WHERE clinic=? AND kind='professionals' AND id=?",(clinic,professional_id)).fetchone()
            if row is None:raise LookupError('Profissional não encontrado')
            name=json.loads(row[0])['nome']
            db.execute("UPDATE records SET data=json_set(data,'$.dentista',?) WHERE clinic=? AND kind='appointments' AND json_extract(data,'$.profissional_id')=?",(name,clinic,professional_id))

    def ensure_patient_attendance(self, clinic, patient_id, data, existing_id=None):
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM records WHERE kind='patients' AND clinic=? AND id=?",(clinic,patient_id)).fetchone():
                raise LookupError('Paciente não encontrado')
            row=db.execute("SELECT data FROM records WHERE kind='patient_links' AND clinic=? AND json_extract(data,'$.patient_id')=?",(clinic,patient_id)).fetchone()
            attendance_id=json.loads(row[0])['attendance_id'] if row else None
            if attendance_id is None:
                if existing_id is not None and db.execute("SELECT 1 FROM records WHERE kind='attendance' AND clinic=? AND id=?",(clinic,existing_id)).fetchone():
                    attendance_id=existing_id
                else:
                    attendance_id=db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)',('attendance',clinic,json.dumps(data))).lastrowid
                db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)',('patient_links',clinic,json.dumps(dict(patient_id=patient_id,attendance_id=attendance_id))))
            row=db.execute("SELECT data FROM records WHERE kind='attendance' AND clinic=? AND id=?",(clinic,attendance_id)).fetchone()
            current=json.loads(row[0])
            current.update(cliente=data['cliente'],iniciais=data['iniciais'])
            db.execute("UPDATE records SET data=? WHERE clinic=? AND id=? AND kind='attendance'",(json.dumps(current),clinic,attendance_id))
        return dict(current,id=attendance_id)

    def delete(self, kind, clinic, identifier):
        with self.connect() as db:
            if kind == 'appointments':
                if not db.in_transaction:
                    db.execute('BEGIN IMMEDIATE')
                completion = db.execute(
                    "SELECT json_extract(data,'$.realizado_em') FROM records WHERE kind=? AND clinic=? AND id=?",
                    (kind, clinic, identifier),
                ).fetchone()
                if completion and completion[0]:
                    raise ValueError('Desfaça a marcação de realizado antes de excluir a consulta.')
            if not db.execute('DELETE FROM records WHERE id=? AND kind=? AND clinic=?', (identifier,kind,clinic)).rowcount:
                raise LookupError('Registro não encontrado')
            if kind == 'attendance':
                db.execute("DELETE FROM records WHERE kind='patient_links' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,identifier))
                db.execute("DELETE FROM records WHERE kind='complaints' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,identifier))
                db.execute("DELETE FROM records WHERE kind IN ('summaries','answer_ratings','attendance_meta') AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,identifier))
            if kind == 'patients':
                db.execute("DELETE FROM records WHERE kind='patient_links' AND clinic=? AND json_extract(data,'$.patient_id')=?",(clinic,identifier))
                db.execute("DELETE FROM records WHERE kind='customer_links' AND clinic=? AND json_extract(data,'$.patient_id')=?",(clinic,identifier))

    def set_summary(self, clinic, attendance_id, data):
        data = dict(data,attendance_id=attendance_id)
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM records WHERE id=? AND kind=? AND clinic=?',(attendance_id,'attendance',clinic)).fetchone():
                raise LookupError('Registro não encontrado')
            row = db.execute("SELECT id FROM records WHERE kind='summaries' AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,attendance_id)).fetchone()
            if row:
                identifier = row[0]
                db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),identifier))
            else:
                identifier = db.execute('INSERT INTO records(kind,clinic,data) VALUES (?,?,?)',('summaries',clinic,json.dumps(data))).lastrowid
        return dict(data,id=identifier)

    def set_complaint(self, clinic, attendance_id, data):
        data = dict(data, attendance_id=attendance_id)
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
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

    def clear_messages(self, clinic, identifier):
        """Apaga o histórico de uma conversa e o que dependia dele (resumo, avaliações, classificação)."""
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            if not db.execute("UPDATE records SET data=json_set(data,'$.mensagens',json('[]')) WHERE id=? AND kind='attendance' AND clinic=?",
                              (identifier,clinic)).rowcount:
                raise LookupError('Registro não encontrado')
            db.execute("DELETE FROM records WHERE kind IN ('summaries','answer_ratings','complaints','attendance_meta') "
                       "AND clinic=? AND json_extract(data,'$.attendance_id')=?",(clinic,identifier))

    def append_message(self, clinic, identifier, message):
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM records WHERE id=? AND kind=? AND clinic=?',(identifier,'attendance',clinic)).fetchone()
            if not row:
                raise LookupError('Registro não encontrado')
            data = json.loads(row[0])
            data.setdefault('mensagens',[]).append(message)
            db.execute('UPDATE records SET data=? WHERE id=? AND kind=? AND clinic=?',(json.dumps(data),identifier,'attendance',clinic))
        return dict(data,id=identifier)

    def move(self, clinic, identifier, delta):
        with self.connect() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
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
