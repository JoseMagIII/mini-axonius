-- Every sync appends rows; nothing is updated in place, so history is queryable.

CREATE TABLE IF NOT EXISTS sync_runs (
    id          serial PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    error       text
);

CREATE TABLE IF NOT EXISTS asset_observations (
    id               bigserial PRIMARY KEY,
    sync_run_id      int NOT NULL REFERENCES sync_runs (id) ON DELETE CASCADE,
    source           text NOT NULL,
    source_id        text NOT NULL,
    hostname         text NOT NULL,
    ip_address       inet,
    os               text,
    software         text,
    software_version text,
    owner            text,
    environment      text,
    state            text,
    raw              jsonb NOT NULL DEFAULT '{}',
    observed_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS asset_observations_run_idx ON asset_observations (sync_run_id, source);

CREATE TABLE IF NOT EXISTS identities (
    id           bigserial PRIMARY KEY,
    sync_run_id  int NOT NULL REFERENCES sync_runs (id) ON DELETE CASCADE,
    source       text NOT NULL,
    username     text NOT NULL,
    email        text,
    full_name    text,
    department   text,
    status       text NOT NULL,
    mfa_enabled  boolean NOT NULL,
    observed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS identities_run_idx ON identities (sync_run_id);

-- NVD results are cached per software version, so a sync doesn't wait on the API every time.
CREATE TABLE IF NOT EXISTS nvd_lookups (
    software         text NOT NULL,
    software_version text NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now(),
    origin           text NOT NULL CHECK (origin IN ('nvd', 'fallback')),
    total_results    int NOT NULL,
    PRIMARY KEY (software, software_version)
);

CREATE TABLE IF NOT EXISTS vulnerabilities (
    software         text NOT NULL,
    software_version text NOT NULL,
    cve_id           text NOT NULL,
    severity         text,
    cvss_score       numeric(3, 1),
    published_at     timestamptz,
    summary          text,
    PRIMARY KEY (software, software_version, cve_id),
    FOREIGN KEY (software, software_version) REFERENCES nvd_lookups ON DELETE CASCADE
);

-- Matches hostnames across sources: "WEB-01.acme.local " and "web-01" become "web-01".
CREATE OR REPLACE FUNCTION normalize_hostname(name text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    RETURN lower(split_part(btrim(name), '.', 1));
