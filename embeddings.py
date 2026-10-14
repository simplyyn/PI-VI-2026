"""Embeddings locais (fastembed/ONNX) e divisão da base de conhecimento em trechos.

Nenhum texto sai do servidor. O modelo é baixado do Hugging Face na primeira utilização
(~220 MB) para FASTEMBED_CACHE_PATH (padrão: pasta temporária do sistema).
"""
import os
import re
import threading

DEFAULT_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
# Deve coincidir com a coluna kb_chunks.embedding vector(384) em migrations/001_schema.sql.
EMBEDDING_DIMENSION = 384

class EmbeddingUnavailable(RuntimeError):
    pass

class FastEmbedEmbedder:
    """Carrega o modelo sob demanda: iniciar a aplicação não baixa nem carrega nada."""
    def __init__(self, model=DEFAULT_MODEL):
        self.model = model
        self._engine = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._engine is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError:
                    raise EmbeddingUnavailable('fastembed não instalado') from None
                try:
                    self._engine = TextEmbedding(self.model, cache_dir=os.getenv('FASTEMBED_CACHE_PATH'))
                except Exception:
                    raise EmbeddingUnavailable('Modelo de embeddings indisponível') from None
        return self._engine

    def _vectors(self, generator):
        try:
            vectors = [[float(x) for x in vector] for vector in generator]
        except EmbeddingUnavailable:
            raise
        except Exception:
            raise EmbeddingUnavailable('Falha ao gerar embeddings') from None
        if any(len(v) != EMBEDDING_DIMENSION for v in vectors):
            raise EmbeddingUnavailable(f'Modelo {self.model} não gera vetores de {EMBEDDING_DIMENSION} dimensões')
        return vectors

    def embed_documents(self, texts):
        return self._vectors(self._load().passage_embed(list(texts)))

    def embed_query(self, text):
        return self._vectors(self._load().query_embed(text))[0]

def create_embedder():
    if os.getenv('SMARTDENT_EMBEDDINGS', 'fastembed').lower() == 'off':
        return None
    return FastEmbedEmbedder(os.getenv('SMARTDENT_EMBEDDING_MODEL') or DEFAULT_MODEL)

def chunk_text(text, size=500, overlap=100):
    """Divide em trechos de ~size caracteres respeitando frases, com sobreposição.

    O modelo padrão foi treinado com sequências de até 128 tokens (~500 caracteres em português).
    """
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= size:
        return [text] if text else []
    pieces = []
    for sentence in re.split(r'(?<=[.!?;:])\s+', text):
        while len(sentence) > size:
            cut = sentence.rfind(' ', 0, size)
            cut = cut if cut > 0 else size
            pieces.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            pieces.append(sentence)
    chunks, current = [], ''
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > size:
            chunks.append(current)
            tail = current[-overlap:]
            current = tail[tail.find(' ') + 1:] if ' ' in tail else ''
        current = f'{current} {piece}'.strip()
    if current:
        chunks.append(current)
    return chunks
