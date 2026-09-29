import pytest

from app.guardrail import check_sql


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM assets_unified",
        "select hostname from gap_missing_edr where environment = 'prod'",
        "WITH prod AS (SELECT * FROM assets_unified WHERE environment = 'prod') SELECT count(*) FROM prod",
        "SELECT hostname FROM gap_missing_edr UNION SELECT hostname FROM gap_ghost_assets",
        "SELECT hostname, row_number() OVER (ORDER BY hostname) FROM assets_unified;",
    ],
)
def test_allows_read_only_queries(statement):
    assert check_sql(statement).allowed


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        ("DELETE FROM asset_observations", "Only SELECT"),
        ("UPDATE identities SET status = 'active'", "Only SELECT"),
        ("DROP TABLE sync_runs", "Only SELECT"),
        ("SELECT 1; DROP TABLE sync_runs", "one statement"),
        ("WITH gone AS (DELETE FROM identities RETURNING *) SELECT * FROM gone", "Delete"),
        ("SELECT * INTO copy_of_assets FROM assets_unified", "Into"),
        ("SELECT pg_sleep(30)", "pg_sleep"),
        ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
        ("SELECT * FROM identities FOR UPDATE", "Lock"),
        ("SET ROLE admin", "Only SELECT"),
        ("COPY identities TO STDOUT", "Only SELECT"),
        ("SELEC hostname FROM", "parse"),
        ("", "empty"),
    ],
)
def test_blocks_anything_that_is_not_a_plain_read(statement, reason):
    result = check_sql(statement)
    assert not result.allowed
    assert reason.lower() in result.reason.lower()


def test_adds_a_row_limit_when_missing():
    assert check_sql("SELECT * FROM assets_unified", row_limit=50).sql.endswith("LIMIT 50")


def test_keeps_a_smaller_existing_limit():
    assert check_sql("SELECT * FROM assets_unified LIMIT 5", row_limit=50).sql.endswith("LIMIT 5")
