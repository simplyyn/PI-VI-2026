"""Apoio aos testes PostgreSQL. Só rodam com SMARTDENT_TEST_DATABASE_URL apontando para um banco descartável:
cada teste cria um schema próprio (search_path) e o remove ao final."""
import hashlib
import os
import re
import secrets
from embeddings import EMBEDDING_DIMENSION, EmbeddingUnavailable

URL = os.getenv('SMARTDENT_TEST_DATABASE_URL', '')
SKIP_REASON = 'defina SMARTDENT_TEST_DATABASE_URL (PostgreSQL descartável com pgvector)'

def fresh_database(testcase):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = 'teste_' + secrets.token_hex(6)
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def drop():
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    testcase.addCleanup(drop)
    return make_conninfo(URL, options=f'-c search_path={schema},public')

class FakeEmbedder:
    """Vetores determinísticos por palavras (sem rede nem modelo): textos sem palavras em comum ficam ortogonais."""
    model = 'teste-bag-of-words'

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def _embed(self, text):
        vector = [0.0] * EMBEDDING_DIMENSION
        for word in re.findall(r'\w{4,}', text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % (EMBEDDING_DIMENSION - 1)] += 1.0
        vector[-1] = 0.0 if any(vector) else 1.0
        return vector

    def embed_documents(self, texts):
        self.calls += 1
        if self.fail:
            raise EmbeddingUnavailable('falha simulada')
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        if self.fail:
            raise EmbeddingUnavailable('falha simulada')
        return self._embed(text)
