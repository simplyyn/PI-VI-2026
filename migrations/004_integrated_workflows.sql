ALTER TABLE appointments ADD COLUMN profissional_id bigint;
ALTER TABLE appointments ADD COLUMN realizado_em date;
ALTER TABLE attendance_messages ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}';

CREATE TABLE workflow_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinic_id text NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    kind text NOT NULL,
    payload jsonb NOT NULL
);
CREATE INDEX workflow_records_scope ON workflow_records(clinic_id, kind, id);
CREATE UNIQUE INDEX workflow_customer_user ON workflow_records (clinic_id, (payload->>'user_id'))
    WHERE kind = 'customer_links';
CREATE UNIQUE INDEX workflow_answer_rating ON workflow_records
    (clinic_id, (payload->>'attendance_id'), (payload->>'message_id'), (payload->>'user_id'))
    WHERE kind = 'answer_ratings';

CREATE TABLE booking_receipts (
    clinic_id text NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    operation_key text NOT NULL,
    appointment_id bigint NOT NULL,
    PRIMARY KEY (clinic_id, operation_key)
);
