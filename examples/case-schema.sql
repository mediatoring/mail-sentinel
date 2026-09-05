-- Synthetic database for testing the case-evidence adapter.
CREATE TABLE cases (
    case_code TEXT PRIMARY KEY,
    disclosure_approved INTEGER NOT NULL CHECK (disclosure_approved IN (0, 1))
);
INSERT INTO cases VALUES ('Case-AbC', 1), ('Case-XYZ', 0);
