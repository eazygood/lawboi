-- Per-section heading text (e.g. "Katseaeg" for TLS § 10¹), read from the
-- source XML's <paragrahvPealkiri>. Nullable: many provisions have none in
-- the source itself, and existing rows predate this column. Run against
-- existing databases; fresh installs get this from db/schema.sql.
ALTER TABLE provision ADD COLUMN IF NOT EXISTS heading TEXT;
