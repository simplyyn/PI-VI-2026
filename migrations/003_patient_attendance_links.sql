-- Vínculo entre pacientes e a conversa principal, sem alterar conversas existentes.
CREATE TABLE patient_attendance_links (
    clinic_id text NOT NULL,
    patient_id bigint NOT NULL,
    attendance_id bigint NOT NULL,
    PRIMARY KEY (clinic_id, patient_id),
    FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE CASCADE,
    FOREIGN KEY (clinic_id, attendance_id) REFERENCES attendances (clinic_id, id) ON DELETE CASCADE
);
