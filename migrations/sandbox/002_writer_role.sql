-- SANDBOX ONLY. No login, password or service-role key is provisioned.
BEGIN;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aql_sandbox_writer') THEN
        CREATE ROLE aql_sandbox_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;
GRANT USAGE ON SCHEMA aql_sandbox TO aql_sandbox_writer;
GRANT INSERT, SELECT ON aql_sandbox.market_bars TO aql_sandbox_writer;
DROP POLICY IF EXISTS sandbox_writer_insert ON aql_sandbox.market_bars;
CREATE POLICY sandbox_writer_insert ON aql_sandbox.market_bars FOR INSERT
    TO aql_sandbox_writer WITH CHECK (true);
DROP POLICY IF EXISTS sandbox_writer_select ON aql_sandbox.market_bars;
CREATE POLICY sandbox_writer_select ON aql_sandbox.market_bars FOR SELECT
    TO aql_sandbox_writer USING (true);
-- Owner grants membership ONLY to a dedicated sandbox login, outside this repo.
COMMIT;
