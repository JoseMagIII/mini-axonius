-- Views are rebuilt on every start, so column changes apply without a migration.
DO $$
DECLARE view_name text;
BEGIN
    FOR view_name IN SELECT viewname FROM pg_views WHERE schemaname = 'public' LOOP
        EXECUTE format('DROP VIEW IF EXISTS %I CASCADE', view_name);
    END LOOP;
END $$;

-- Rows from the most recent successful sync only; older runs stay for history queries.
CREATE VIEW latest_observations AS
WITH latest_run AS (
    SELECT max(id) AS id FROM sync_runs WHERE status = 'succeeded'
),
ranked AS (
    SELECT o.*,
           normalize_hostname(o.hostname) AS asset_key,
           row_number() OVER (
               PARTITION BY o.source, normalize_hostname(o.hostname)
               ORDER BY o.observed_at DESC, o.id DESC
           ) AS rank_in_source
    FROM asset_observations o
    JOIN latest_run r ON o.sync_run_id = r.id
)
SELECT * FROM ranked WHERE rank_in_source = 1;

CREATE VIEW latest_identities AS
SELECT i.*
FROM identities i
WHERE i.sync_run_id = (SELECT max(id) FROM sync_runs WHERE status = 'succeeded');

-- One row per real asset, merged from every source that reports it.
CREATE VIEW assets_unified AS
WITH history AS (
    SELECT normalize_hostname(o.hostname) AS asset_key,
           min(o.observed_at) AS first_seen,
           max(o.observed_at) AS last_seen
    FROM asset_observations o
    JOIN sync_runs r ON r.id = o.sync_run_id AND r.status = 'succeeded'
    GROUP BY 1
)
SELECT l.asset_key AS hostname,
       array_agg(l.source ORDER BY l.source) AS sources,
       bool_or(l.source = 'docker') AS in_docker,
       bool_or(l.source = 'edr') AS has_edr,
       max(l.state) FILTER (WHERE l.source = 'docker') AS docker_state,
       max(l.state) FILTER (WHERE l.source = 'edr') AS edr_status,
       max((l.raw ->> 'last_checkin')::timestamptz) FILTER (WHERE l.source = 'edr') AS edr_last_checkin,
       max(host(l.ip_address)) FILTER (WHERE l.source = 'docker') AS ip_address,
       coalesce(max(l.os) FILTER (WHERE l.source = 'edr'), max(l.os)) AS os,
       max(l.software) FILTER (WHERE l.source = 'docker') AS software,
       max(l.software_version) FILTER (WHERE l.source = 'docker') AS software_version,
       max(l.owner) FILTER (WHERE l.source = 'docker') AS owner,
       max(l.environment) FILTER (WHERE l.source = 'docker') AS environment,
       h.first_seen,
       h.last_seen
FROM latest_observations l
JOIN history h USING (asset_key)
GROUP BY l.asset_key, h.first_seen, h.last_seen;

-- Running servers with no EDR agent reporting in.
CREATE VIEW gap_missing_edr AS
SELECT hostname, software, software_version, owner, environment, ip_address
FROM assets_unified
WHERE in_docker AND docker_state = 'running' AND NOT has_edr
ORDER BY environment = 'prod' DESC, hostname;

-- Servers whose software version has known CVEs, worst first.
CREATE VIEW gap_vulnerable_software AS
SELECT a.hostname,
       a.software,
       a.software_version,
       a.owner,
       a.environment,
       count(v.cve_id) AS cve_count,
       count(*) FILTER (WHERE v.severity IN ('CRITICAL', 'HIGH')) AS high_or_critical,
       max(v.cvss_score) AS max_cvss,
       (array_agg(v.cve_id ORDER BY v.cvss_score DESC NULLS LAST, v.cve_id))[1:5] AS top_cves
FROM assets_unified a
JOIN vulnerabilities v USING (software, software_version)
WHERE a.in_docker
GROUP BY a.hostname, a.software, a.software_version, a.owner, a.environment
ORDER BY max_cvss DESC NULLS LAST, cve_count DESC;

-- Servers owned by someone who is disabled or unknown to the identity provider.
CREATE VIEW gap_orphaned_owner AS
SELECT a.hostname,
       a.owner,
       a.environment,
       coalesce(i.status, 'not found') AS owner_status,
       CASE WHEN i.username IS NULL THEN 'Owner not in identity provider'
            ELSE 'Owner account is disabled' END AS reason
FROM assets_unified a
LEFT JOIN latest_identities i ON i.username = a.owner
WHERE a.in_docker AND (i.username IS NULL OR i.status <> 'active')
ORDER BY a.hostname;

-- EDR still reports these, but they aren't running: stale records or decommissioned hosts.
CREATE VIEW gap_ghost_assets AS
SELECT hostname,
       edr_status,
       docker_state,
       CASE WHEN NOT in_docker THEN 'Not found in Docker'
            ELSE 'Container is ' || docker_state END AS reason,
       edr_last_checkin
FROM assets_unified
WHERE has_edr AND (NOT in_docker OR docker_state <> 'running')
ORDER BY hostname;
