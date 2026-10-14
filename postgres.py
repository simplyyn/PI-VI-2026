"""Adaptador PostgreSQL/pgvector definitivo. Preserva o contrato de persistence.Repository.

Concentra todo o SQL do PostgreSQL: esquema relacional (migrations/), isolamento por clínica,
movimentação atômica de estoque e busca híbrida (pgvector + texto completo) na base de conhecimento.
"""
import logging
import re
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from embeddings import EmbeddingUnavailable, chunk_text

log = logging.getLogger('smartdent.postgres')
MIGRATIONS = Path(__file__).with_name('migrations')
MIGRATION_LOCK = 7406221026
CONTEXT_LIMIT = 6000  # mesmo corte por documento aplicado pelo AttendanceAgent
CANDIDATES = 24
RRF_K = 60

def _parse(parser):
    return lambda value: parser(value) if isinstance(value, str) else value

def _format(formatter):
    return lambda value: None if value is None else formatter(value)

# (entrada no banco, saída na API): os mesmos formatos que o SQLite provisório devolve.
PLAIN = (lambda value: value, lambda value: value)
DATE = (_parse(date.fromisoformat), _format(date.isoformat))
TIME = (_parse(time.fromisoformat), _format(time.isoformat))
STAMP = (_parse(datetime.fromisoformat), _format(lambda value: value.astimezone(timezone.utc).isoformat()))
BR_DATE = (_parse(lambda value: datetime.strptime(value, '%d/%m/%Y').date()), _format(lambda value: value.strftime('%d/%m/%Y')))

TABLES = {
    'kb': ('kb_articles', dict(titulo=PLAIN, categoria=PLAIN, conteudo=PLAIN, status=PLAIN, views=PLAIN, atualizado=BR_DATE)),
    'stock': ('stock_items', dict(nome=PLAIN, categoria=PLAIN, unidade=PLAIN, quantidade=PLAIN, minimo=PLAIN)),
    'patients': ('patients', dict(nome=PLAIN, telefone=PLAIN, email=PLAIN, status=PLAIN, plano=PLAIN, ultima_consulta=DATE,
                                  proxima_consulta=DATE, procedimentos=PLAIN, iniciais=PLAIN, cor=PLAIN, criado_em=STAMP)),
    'appointments': ('appointments', dict(paciente_id=PLAIN, data=DATE, horario=TIME, duracao=PLAIN, procedimento=PLAIN,
                                          dentista=PLAIN, status=PLAIN, cor=PLAIN, criado_em=STAMP)),
    'attendance': ('attendances', dict(cliente=PLAIN, preview=PLAIN, status=PLAIN, canal=PLAIN, iniciais=PLAIN, cor=PLAIN,
                                       hora=PLAIN, criado_em=STAMP)),
    'complaints': ('complaint_classifications', dict(attendance_id=PLAIN, reclamacao=PLAIN, categoria=PLAIN, motivo=PLAIN,
                                                     origem=PLAIN, modelo=PLAIN, classificado_em=STAMP)),
}

USER_SQL = '''SELECT u.id, u.email, u.nome, u.iniciais, u.role, u.password_hash,
                     coalesce(u.clinic_id, '') AS empresa_id, coalesce(c.nome, '') AS empresa,
                     coalesce(c.nome, '') AS empresa_nome, coalesce(c.plano, '') AS plano
              FROM users u LEFT JOIN clinics c ON c.id = u.clinic_id WHERE '''

def _names(names):
    return sql.SQL(', ').join(map(sql.Identifier, names))

def _vector(values):
    return '[' + ','.join(format(value, '.8g') for value in values) + ']'

def _version(text):
    return tuple(int(part) for part in re.findall(r'\d+', text)[:2])

def migrate(conninfo):
    """Aplica migrations/*.sql pendentes, em ordem, cada uma em sua transação. Retorna as aplicadas."""
    applied = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute('SELECT pg_advisory_lock(%s)', (MIGRATION_LOCK,))
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations '
                         '(versao text PRIMARY KEY, aplicada_em timestamptz NOT NULL DEFAULT now())')
            done = {row[0] for row in conn.execute('SELECT versao FROM schema_migrations')}
            for path in sorted(MIGRATIONS.glob('*.sql')):
                if path.stem not in done:
                    with conn.transaction():
                        conn.execute(path.read_text(encoding='utf-8'))
                        conn.execute('INSERT INTO schema_migrations (versao) VALUES (%s)', (path.stem,))
                    applied.append(path.stem)
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (MIGRATION_LOCK,))
    return applied

class PostgresRepository:
    supports_semantic_search = True

    def __init__(self, conninfo, embedder=None, max_distance=0.7, pool_size=10, migrate_schema=True):
        if migrate_schema:
            migrate(conninfo)
        self.embedder = embedder
        self.max_distance = max_distance
        self.pool = ConnectionPool(conninfo, min_size=1, max_size=pool_size, kwargs={'row_factory': dict_row},
                                   check=ConnectionPool.check_connection, name='smartdent', open=True)
        try:
            self.pool.wait(timeout=15)
            with self.pool.connection() as conn:
                row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        except Exception:
            self.pool.close()
            raise
        # A partir do pgvector 0.8, a busca HNSW filtrada por clínica continua até achar candidatos suficientes.
        self.iterative_scan = row is not None and _version(row['extversion']) >= (0, 8)

    def close(self):
        self.pool.close()

    @contextmanager
    def _transaction(self):
        with self.pool.connection() as conn:
            try:
                yield conn
            except (psycopg.IntegrityError, psycopg.DataError) as exc:
                raise ValueError('Dados rejeitados pelo banco') from exc

    # ─── Usuários ────────────────────────────────────────────────────────────

    def user(self, email):
        with self._transaction() as conn:
            return conn.execute(USER_SQL + 'u.email = %s', (email.strip().lower(),)).fetchone()

    def user_by_id(self, user_id):
        with self._transaction() as conn:
            return conn.execute(USER_SQL + 'u.id = %s', (user_id,)).fetchone()

    def add_user(self, data):
        data = dict(data, email=data['email'].strip().lower())
        clinic = (data.get('empresa_id') or '').strip() or None
        with self._transaction() as conn:
            if clinic:
                conn.execute('INSERT INTO clinics (id, nome, plano) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING',
                             (clinic, data.get('empresa_nome') or clinic, data.get('plano') or ''))
            try:
                row = conn.execute('INSERT INTO users (email, nome, iniciais, role, clinic_id, password_hash) '
                                   'VALUES (%s, %s, %s, %s, %s, %s) RETURNING id',
                                   (data['email'], data.get('nome', ''), data.get('iniciais', ''), data['role'], clinic,
                                    data['password_hash'])).fetchone()
            except psycopg.errors.UniqueViolation:
                raise ValueError('E-mail já cadastrado') from None
        return dict(data, id=row['id'])

    # ─── Registros por clínica ───────────────────────────────────────────────

    def _spec(self, kind):
        if kind not in TABLES:
            raise TypeError(f'Tipo de registro sem tabela: {kind}')
        return TABLES[kind]

    def _row(self, kind, row, messages=None):
        columns = TABLES[kind][1]
        record = {name: convert[1](row[name]) for name, convert in columns.items()}
        record['id'] = row['id']
        if kind == 'attendance':
            record['mensagens'] = messages or []
        return record

    def _messages(self, conn, clinic, attendance_id=None):
        query, params = 'SELECT attendance_id, texto, autor, criado_em FROM attendance_messages WHERE clinic_id = %s', [clinic]
        if attendance_id is not None:
            query, params = query + ' AND attendance_id = %s', params + [attendance_id]
        grouped = {}
        for row in conn.execute(query + ' ORDER BY id', params):
            grouped.setdefault(row['attendance_id'], []).append(
                dict(texto=row['texto'], autor=row['autor'], criado_em=STAMP[1](row['criado_em'])))
        return grouped

    def list(self, kind, clinic):
        table, columns = self._spec(kind)
        query = sql.SQL('SELECT id, {} FROM {} WHERE clinic_id = %s ORDER BY id').format(_names(columns), sql.Identifier(table))
        with self._transaction() as conn:
            rows = conn.execute(query, (clinic,)).fetchall()
            messages = self._messages(conn, clinic) if kind == 'attendance' else {}
        return [self._row(kind, row, messages.get(row['id'])) for row in rows]

    def save(self, kind, clinic, data, identifier=None):
        table, columns = self._spec(kind)
        unknown = set(data) - set(columns) - ({'mensagens'} if kind == 'attendance' else set())
        if unknown:
            raise TypeError(f'Campos sem coluna em {table}: {sorted(unknown)}')
        values = {name: columns[name][0](data[name]) for name in columns if name in data}
        chunks = self._prepare_index(clinic, data, identifier) if kind == 'kb' else None
        with self._transaction() as conn:
            if identifier is None:
                query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING id, {}').format(
                    sql.Identifier(table), _names(['clinic_id', *values]),
                    sql.SQL(', ').join([sql.Placeholder()] * (len(values) + 1)), _names(columns))
                row = conn.execute(query, [clinic, *values.values()]).fetchone()
                for message in data.get('mensagens', []) if kind == 'attendance' else []:
                    self._insert_message(conn, clinic, row['id'], message)
            else:
                # Substituição completa, como no SQLite: campo ausente volta ao padrão da coluna.
                assignments = [sql.SQL('{} = %s' if name in values else '{} = DEFAULT').format(sql.Identifier(name))
                               for name in columns]
                query = sql.SQL('UPDATE {} SET {} WHERE id = %s AND clinic_id = %s RETURNING id, {}').format(
                    sql.Identifier(table), sql.SQL(', ').join(assignments), _names(columns))
                row = conn.execute(query, [*values.values(), identifier, clinic]).fetchone()
                if row is None:
                    raise LookupError('Registro não encontrado')
            if kind == 'kb':
                self._write_index(conn, clinic, row['id'], chunks)
            messages = self._messages(conn, clinic, row['id']).get(row['id']) if kind == 'attendance' else None
        return self._row(kind, row, messages)

    def delete(self, kind, clinic, identifier):
        table, _ = self._spec(kind)
        query = sql.SQL('DELETE FROM {} WHERE id = %s AND clinic_id = %s').format(sql.Identifier(table))
        with self._transaction() as conn:
            if conn.execute(query, (identifier, clinic)).rowcount == 0:
                raise LookupError('Registro não encontrado')

    def move(self, clinic, identifier, delta):
        with self._transaction() as conn:
            row = conn.execute('SELECT quantidade FROM stock_items WHERE id = %s AND clinic_id = %s FOR UPDATE',
                               (identifier, clinic)).fetchone()
            if row is None:
                raise LookupError('Registro não encontrado')
            quantity = row['quantidade'] + delta
            if quantity < 0 or quantity > 1000000000:
                raise ValueError('Saldo inválido')
            query = sql.SQL('UPDATE stock_items SET quantidade = %s WHERE id = %s AND clinic_id = %s RETURNING id, {}').format(
                _names(TABLES['stock'][1]))
            updated = conn.execute(query, (quantity, identifier, clinic)).fetchone()
            conn.execute('INSERT INTO stock_movements (clinic_id, stock_item_id, delta, saldo) VALUES (%s, %s, %s, %s)',
                         (clinic, identifier, delta, quantity))
        return self._row('stock', updated)

    def _insert_message(self, conn, clinic, attendance_id, message):
        conn.execute('INSERT INTO attendance_messages (clinic_id, attendance_id, texto, autor, criado_em) '
                     'VALUES (%s, %s, %s, %s, coalesce(%s::timestamptz, now()))',
                     (clinic, attendance_id, message['texto'], message['autor'], STAMP[0](message.get('criado_em'))))

    def append_message(self, clinic, identifier, message):
        query = sql.SQL('SELECT id, {} FROM attendances WHERE id = %s AND clinic_id = %s FOR SHARE').format(
            _names(TABLES['attendance'][1]))
        with self._transaction() as conn:
            row = conn.execute(query, (identifier, clinic)).fetchone()
            if row is None:
                raise LookupError('Registro não encontrado')
            self._insert_message(conn, clinic, identifier, message)
            messages = self._messages(conn, clinic, identifier).get(identifier)
        return self._row('attendance', row, messages)

    # ─── Reclamações (RF005) ─────────────────────────────────────────────────

    def set_complaint(self, clinic, attendance_id, data):
        _, columns = TABLES['complaints']
        values = {name: columns[name][0](data[name]) for name in columns if name in data and name != 'attendance_id'}
        query = sql.SQL('INSERT INTO complaint_classifications ({}) VALUES ({}) '
                        'ON CONFLICT (clinic_id, attendance_id) DO UPDATE SET {} RETURNING id, {}').format(
            _names(['clinic_id', 'attendance_id', *values]),
            sql.SQL(', ').join([sql.Placeholder()] * (len(values) + 2)),
            sql.SQL(', ').join(sql.SQL('{0} = EXCLUDED.{0}').format(sql.Identifier(name)) for name in values),
            _names(columns))
        with self._transaction() as conn:
            try:
                row = conn.execute(query, [clinic, attendance_id, *values.values()]).fetchone()
            except psycopg.errors.ForeignKeyViolation:
                raise LookupError('Registro não encontrado') from None
        return self._row('complaints', row)

    def delete_complaint(self, clinic, attendance_id):
        with self._transaction() as conn:
            if conn.execute('DELETE FROM complaint_classifications WHERE clinic_id = %s AND attendance_id = %s',
                            (clinic, attendance_id)).rowcount == 0:
                raise LookupError('Registro não encontrado')

    # ─── Busca semântica (pgvector) ──────────────────────────────────────────

    def _embed_article(self, titulo, conteudo):
        """Trechos com embeddings; [] remove o índice do artigo (sem embedder ou falha do modelo)."""
        if self.embedder is None:
            return []
        parts = chunk_text(conteudo)
        try:
            vectors = self.embedder.embed_documents([f'{titulo}\n{part}' for part in parts])
        except EmbeddingUnavailable as exc:
            log.warning('Artigo salvo sem índice semântico (%s); execute manage.py reindex', exc)
            return []
        return [(ordem, part, _vector(vector)) for ordem, (part, vector) in enumerate(zip(parts, vectors))]

    def _prepare_index(self, clinic, data, identifier):
        """Calcula embeddings fora da transação. None mantém os trechos atuais (texto inalterado)."""
        titulo, conteudo = data.get('titulo', ''), data.get('conteudo', '')
        if identifier is not None:
            with self._transaction() as conn:
                current = conn.execute(
                    'SELECT titulo, conteudo, EXISTS (SELECT 1 FROM kb_chunks c WHERE c.article_id = a.id AND c.modelo = %s) AS indexado '
                    'FROM kb_articles a WHERE id = %s AND clinic_id = %s',
                    (self.embedder.model if self.embedder else '', identifier, clinic)).fetchone()
            if current and (current['titulo'], current['conteudo']) == (titulo, conteudo) and (current['indexado'] or self.embedder is None):
                return None
        return self._embed_article(titulo, conteudo)

    def _write_index(self, conn, clinic, article_id, chunks):
        if chunks is None:
            return
        conn.execute('DELETE FROM kb_chunks WHERE clinic_id = %s AND article_id = %s', (clinic, article_id))
        if chunks:
            with conn.cursor() as cursor:
                cursor.executemany('INSERT INTO kb_chunks (clinic_id, article_id, ordem, conteudo, embedding, modelo) '
                                   'VALUES (%s, %s, %s, %s, %s::vector, %s)',
                                   [(clinic, article_id, ordem, texto, vetor, self.embedder.model) for ordem, texto, vetor in chunks])

    def reindex(self, force=False):
        """Gera embeddings dos artigos sem índice do modelo atual (ou de todos, com force). Retorna a quantidade."""
        if self.embedder is None:
            raise EmbeddingUnavailable('Embeddings desativados (SMARTDENT_EMBEDDINGS=off)')
        with self._transaction() as conn:
            rows = conn.execute('SELECT a.id, a.clinic_id, a.titulo, a.conteudo FROM kb_articles a WHERE %(force)s OR NOT EXISTS '
                                '(SELECT 1 FROM kb_chunks c WHERE c.article_id = a.id AND c.modelo = %(modelo)s) ORDER BY a.id',
                                dict(force=force, modelo=self.embedder.model)).fetchall()
        count = 0
        for row in rows:
            parts = chunk_text(row['conteudo'])
            vectors = self.embedder.embed_documents([f"{row['titulo']}\n{part}" for part in parts])
            chunks = [(ordem, part, _vector(vector)) for ordem, (part, vector) in enumerate(zip(parts, vectors))]
            with self._transaction() as conn:
                # Ignora o artigo se ele foi editado durante o cálculo: o salvamento já reindexou.
                if conn.execute('SELECT 1 FROM kb_articles WHERE id = %s AND titulo = %s AND conteudo = %s FOR UPDATE',
                                (row['id'], row['titulo'], row['conteudo'])).fetchone():
                    self._write_index(conn, row['clinic_id'], row['id'], chunks)
                    count += 1
        return count

    def search_knowledge(self, clinic, question, limit=4):
        """Busca híbrida: similaridade de cosseno (pgvector) + texto completo em português, fundidas por RRF.

        Só artigos ativos da clínica. Trechos acima de max_distance não contam como contexto.
        """
        if self.embedder is None:
            raise EmbeddingUnavailable('Embeddings desativados (SMARTDENT_EMBEDDINGS=off)')
        vector = _vector(self.embedder.embed_query(question))
        terms = ' or '.join(dict.fromkeys(re.findall(r'\w{3,}', question.lower()))) or ''
        with self._transaction() as conn:
            conn.execute('SET LOCAL hnsw.ef_search = 100')
            if self.iterative_scan:
                conn.execute('SET LOCAL hnsw.iterative_scan = strict_order')
            chunks = conn.execute(
                'SELECT c.article_id, c.ordem, c.conteudo, c.embedding <=> %(v)s::vector AS distancia '
                'FROM kb_chunks c JOIN kb_articles a ON a.clinic_id = c.clinic_id AND a.id = c.article_id '
                'WHERE c.clinic_id = %(clinic)s AND c.modelo = %(modelo)s AND a.status '
                'ORDER BY c.embedding <=> %(v)s::vector LIMIT %(k)s',
                dict(v=vector, clinic=clinic, modelo=self.embedder.model, k=CANDIDATES)).fetchall()
            lexical = conn.execute(
                "SELECT a.id FROM kb_articles a, websearch_to_tsquery('portuguese', %(terms)s) q "
                'WHERE a.clinic_id = %(clinic)s AND a.status AND a.busca @@ q '
                'ORDER BY ts_rank_cd(a.busca, q) DESC, a.id LIMIT %(k)s',
                dict(terms=terms, clinic=clinic, k=CANDIDATES)).fetchall() if terms else []
            matched = {}
            for chunk in chunks:
                if chunk['distancia'] <= self.max_distance:
                    matched.setdefault(chunk['article_id'], []).append(chunk)
            ranks = [{article_id: rank for rank, article_id in enumerate(matched, 1)},
                     {row['id']: rank for rank, row in enumerate(lexical, 1)}]
            scores = {}
            for rank in ranks:
                for article_id, position in rank.items():
                    scores[article_id] = scores.get(article_id, 0) + 1 / (RRF_K + position)
            ids = sorted(scores, key=lambda article_id: (-scores[article_id], article_id))[:limit]
            articles = {row['id']: row for row in conn.execute(
                'SELECT id, titulo, categoria, conteudo FROM kb_articles WHERE clinic_id = %s AND status AND id = ANY(%s)',
                (clinic, ids))}
        results = []
        for article_id in ids:
            article = articles.get(article_id)
            if article is None:
                continue
            parts = matched.get(article_id, [])
            best = min(parts, key=lambda chunk: chunk['distancia']) if parts else None
            conteudo = article['conteudo']
            if len(conteudo) > CONTEXT_LIMIT and parts:
                conteudo = '\n[...]\n'.join(chunk['conteudo'] for chunk in sorted(parts, key=lambda chunk: chunk['ordem']))
            results.append(dict(id=article_id, titulo=article['titulo'], categoria=article['categoria'], conteudo=conteudo,
                                status=True, empresa_id=clinic, score=round(scores[article_id], 6),
                                distancia=round(float(best['distancia']), 4) if best else None,
                                trecho=best['conteudo'] if best else article['conteudo'][:500]))
        return results
