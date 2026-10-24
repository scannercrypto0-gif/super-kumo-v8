-- SANDBOX ONLY. Owner applies to an isolated project with a dedicated DB role.
-- Never use a production service-role credential. No public PostgREST grants.
BEGIN;
CREATE SCHEMA IF NOT EXISTS aql_sandbox;
CREATE TABLE IF NOT EXISTS aql_sandbox.market_bars (
    symbol text NOT NULL,
    interval text NOT NULL,
    bar_open bigint NOT NULL,
    bar_close bigint NOT NULL CHECK (bar_close >= bar_open),
    open double precision NOT NULL,
    high double precision NOT NULL,
    low double precision NOT NULL,
    close double precision NOT NULL,
    volume double precision NOT NULL,
    is_final boolean NOT NULL CHECK (is_final),
    source text NOT NULL,
    ingested_at bigint NOT NULL,
    committed_at bigint,
    checksum text NOT NULL,
    state text NOT NULL,
    PRIMARY KEY(symbol, interval, bar_open)
);
ALTER TABLE aql_sandbox.market_bars ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON SCHEMA aql_sandbox FROM PUBLIC;
REVOKE ALL ON aql_sandbox.market_bars FROM PUBLIC;
-- The owner provisions a dedicated, sandbox-only login role and grants USAGE,
-- INSERT and SELECT explicitly. RLS policies must be scoped to that role.
-- No role, password, permissive PUBLIC policy, or service key is created here.
COMMIT;
