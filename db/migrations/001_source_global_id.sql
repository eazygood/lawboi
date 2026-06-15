-- Track the Riigi Teataja redaktsioon (globaalID) ingested for each act_version,
-- so the incremental corpus crawl can skip unchanged acts before fetching their XML.
-- Run against existing databases; fresh installs get this from db/schema.sql.
ALTER TABLE act_version ADD COLUMN IF NOT EXISTS source_global_id BIGINT;
CREATE INDEX IF NOT EXISTS act_version_source_global_id_idx
    ON act_version (source_global_id);
