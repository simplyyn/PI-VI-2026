-- SmartDent AI: esquema definitivo (PostgreSQL 14+ com pgvector >= 0.5).
-- Aplicado uma única vez, em transação, por postgres.migrate() (manage.py migrate ou inicialização).
-- Isolamento multi-clínica: toda tabela de dados carrega clinic_id, e as chaves estrangeiras
-- compostas (clinic_id, id) impedem que um registro aponte para outro de clínica diferente.
-- As colunas usam os mesmos nomes dos campos da API para manter o contrato do repositório.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE clinics (
    id         text PRIMARY KEY CHECK (btrim(id) <> ''),
    nome       text NOT NULL,
    plano      text NOT NULL DEFAULT '',
    status     text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo')),
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email          text NOT NULL UNIQUE CHECK (email = lower(btrim(email)) AND email LIKE '%@%'),
    nome           text NOT NULL DEFAULT '',
    iniciais       text NOT NULL DEFAULT '',
    role           text NOT NULL CHECK (role IN ('admin', 'owner', 'customer')),
    clinic_id      text REFERENCES clinics (id),
    password_hash  text NOT NULL,
    criado_em      timestamptz NOT NULL DEFAULT now(),
    CHECK (role = 'admin' OR clinic_id IS NOT NULL)
);
CREATE INDEX users_clinic ON users (clinic_id);

-- Base de conhecimento (RF001): procedimentos, convênios, preços e políticas são artigos categorizados.
CREATE TABLE kb_articles (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id   text NOT NULL REFERENCES clinics (id),
    titulo      text NOT NULL,
    categoria   text NOT NULL,
    conteudo    text NOT NULL,
    status      boolean NOT NULL DEFAULT true,
    views       integer NOT NULL DEFAULT 0 CHECK (views >= 0),
    atualizado  date NOT NULL DEFAULT current_date,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    busca       tsvector GENERATED ALWAYS AS (
                    to_tsvector('portuguese', titulo || ' ' || categoria || ' ' || conteudo)) STORED,
    UNIQUE (clinic_id, id)
);
CREATE INDEX kb_articles_clinic ON kb_articles (clinic_id, id);
CREATE INDEX kb_articles_busca ON kb_articles USING gin (busca);

-- Trechos indexados para busca semântica. A dimensão acompanha embeddings.EMBEDDING_DIMENSION;
-- trocar para um modelo de outra dimensão exige nova migração e manage.py reindex --todos.
CREATE TABLE kb_chunks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id   text NOT NULL,
    article_id  bigint NOT NULL,
    ordem       integer NOT NULL CHECK (ordem >= 0),
    conteudo    text NOT NULL,
    embedding   vector(384) NOT NULL,
    modelo      text NOT NULL,
    FOREIGN KEY (clinic_id, article_id) REFERENCES kb_articles (clinic_id, id) ON DELETE CASCADE,
    UNIQUE (article_id, ordem)
);
CREATE INDEX kb_chunks_article ON kb_chunks (clinic_id, article_id);
CREATE INDEX kb_chunks_embedding ON kb_chunks USING hnsw (embedding vector_cosine_ops);

-- Estoque (RF009) com histórico de movimentações.
CREATE TABLE stock_items (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id   text NOT NULL REFERENCES clinics (id),
    nome        text NOT NULL,
    categoria   text NOT NULL,
    unidade     text NOT NULL,
    quantidade  integer NOT NULL CHECK (quantidade BETWEEN 0 AND 1000000000),
    minimo      integer NOT NULL CHECK (minimo BETWEEN 0 AND 1000000000),
    criado_em   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (clinic_id, id)
);
CREATE INDEX stock_items_clinic ON stock_items (clinic_id, id);

CREATE TABLE stock_movements (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id      text NOT NULL,
    stock_item_id  bigint NOT NULL,
    delta          integer NOT NULL CHECK (delta <> 0),
    saldo          integer NOT NULL CHECK (saldo BETWEEN 0 AND 1000000000),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (clinic_id, stock_item_id) REFERENCES stock_items (clinic_id, id) ON DELETE CASCADE
);
CREATE INDEX stock_movements_item ON stock_movements (clinic_id, stock_item_id, criado_em);

CREATE TABLE patients (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id         text NOT NULL REFERENCES clinics (id),
    nome              text NOT NULL,
    telefone          text NOT NULL DEFAULT '',
    email             text NOT NULL DEFAULT '',
    status            text NOT NULL DEFAULT 'novo' CHECK (status IN ('ativo', 'novo', 'inativo')),
    plano             text NOT NULL DEFAULT '',
    ultima_consulta   date,
    proxima_consulta  date,
    procedimentos     integer NOT NULL DEFAULT 0 CHECK (procedimentos >= 0),
    iniciais          text NOT NULL DEFAULT '',
    cor               text NOT NULL DEFAULT '',
    criado_em         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (clinic_id, id)
);
CREATE INDEX patients_clinic ON patients (clinic_id, id);

CREATE TABLE appointments (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id     text NOT NULL,
    paciente_id   bigint NOT NULL,
    data          date NOT NULL,
    horario       time NOT NULL,
    duracao       integer NOT NULL CHECK (duracao BETWEEN 1 AND 1440),
    procedimento  text NOT NULL,
    dentista      text NOT NULL,
    status        text NOT NULL DEFAULT 'pendente' CHECK (status IN ('confirmado', 'pendente', 'cancelado')),
    cor           text NOT NULL DEFAULT '',
    criado_em     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (clinic_id, paciente_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
    UNIQUE (clinic_id, id)
);
CREATE INDEX appointments_agenda ON appointments (clinic_id, data, horario);
CREATE INDEX appointments_patient ON appointments (clinic_id, paciente_id);

-- Conversas/atendimentos e suas mensagens.
CREATE TABLE attendances (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id  text NOT NULL REFERENCES clinics (id),
    cliente    text NOT NULL,
    preview    text NOT NULL,
    status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('resolved', 'pending', 'escalated')),
    canal      text NOT NULL DEFAULT 'human' CHECK (canal IN ('human', 'ai')),
    iniciais   text NOT NULL DEFAULT '',
    cor        text NOT NULL DEFAULT '',
    hora       text NOT NULL DEFAULT '',
    criado_em  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (clinic_id, id)
);
CREATE INDEX attendances_clinic ON attendances (clinic_id, id);

CREATE TABLE attendance_messages (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id      text NOT NULL,
    attendance_id  bigint NOT NULL,
    texto          text NOT NULL,
    autor          text NOT NULL,
    criado_em      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (clinic_id, attendance_id) REFERENCES attendances (clinic_id, id) ON DELETE CASCADE
);
CREATE INDEX attendance_messages_conversa ON attendance_messages (clinic_id, attendance_id, id);

-- Reclamações (RF005): no máximo uma classificação por atendimento. reclamacao = false registra que o
-- atendimento foi analisado e não contém reclamação, para não ser reenviado ao modelo.
CREATE TABLE complaint_classifications (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id        text NOT NULL,
    attendance_id    bigint NOT NULL,
    reclamacao       boolean NOT NULL,
    categoria        text,
    motivo           text NOT NULL DEFAULT '',
    origem           text NOT NULL CHECK (origem IN ('ia', 'manual')),
    modelo           text NOT NULL DEFAULT '',
    classificado_em  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (clinic_id, attendance_id) REFERENCES attendances (clinic_id, id) ON DELETE CASCADE,
    UNIQUE (clinic_id, attendance_id),
    CHECK (reclamacao = (categoria IS NOT NULL))
);
CREATE INDEX complaint_classifications_relatorio ON complaint_classifications (clinic_id, reclamacao, categoria);
