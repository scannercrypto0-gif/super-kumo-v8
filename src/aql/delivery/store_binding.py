"""Versioned, explicitly enrolled finite synthetic store writers.

The source lock serializes cooperating readers/writers. A committed source intent
precedes the separate store transaction. A crash leaves denial, not cross-file
atomicity or an inferred successful write. No filesystem/hostile-Python boundary.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from ..archive.contracts import canonical, digest
from ..g1_integrity import ContentConflictError, content, record_event, require_eligible_db
from ..models.bar import MarketBar
from .authority import Authority, Limits, PublicationDenied, _append, _project

WRITER = "operational-store-v2"


@contextmanager
def existing(path, timeout=2):
    if not Path(path).is_file():
        raise PublicationDenied("Bound database missing")
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True,
                           isolation_level=None, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA synchronous=FULL")
        yield conn
    finally:
        conn.close()


def has_binding(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='core128_store_link'").fetchone())


def state_digest(conn, limits):
    rows = [dict(r) for r in conn.execute("SELECT * FROM market_bars ORDER BY id")]
    events = [dict(r) for r in conn.execute("SELECT * FROM g1_integrity_events ORDER BY event_id")]
    value = dict(rows=rows, events=events)
    if len(rows) > limits.max_records or len(events) > limits.max_events or len(canonical(value)) > limits.max_bytes:
        raise PublicationDenied("Bound store exceeds frozen synthetic capacity")
    return digest(value)


def freeze_stores(authority, stores):
    """Enrollment is explicit, empty-store only, and never inferred from keys."""
    generation = uuid.uuid4().hex
    bindings, seen = [], set()
    for store in stores:
        from ..storage.operational_store import OperationalStore
        if type(store) is not OperationalStore:
            raise PublicationDenied("Only the registered fenced SQLite adapter is supported")
        path = str(Path(store.db_path).resolve())
        if path == authority.anchor['path'] or path in seen:
            raise PublicationDenied("Distinct explicit store identities required")
        seen.add(path)
        with existing(path) as conn:
            if has_binding(conn) or conn.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0] or conn.execute("SELECT COUNT(*) FROM g1_integrity_events").fetchone()[0]:
                raise PublicationDenied("Enroll a fresh empty synthetic store; no legacy conversion")
            binding = dict(schema="aql.source-store-binding.v1", source=authority.anchor['source'],
                           source_path=authority.anchor['path'], generation=generation,
                           path=path, store=uuid.uuid4().hex, writer=WRITER)
            conn.executescript("""
                CREATE TABLE core128_store_link(singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL);
                CREATE TRIGGER core128_link_no_update BEFORE UPDATE ON core128_store_link BEGIN
                  SELECT RAISE(ABORT,'immutable source binding'); END;
                CREATE TRIGGER core128_link_no_delete BEFORE DELETE ON core128_store_link BEGIN
                  SELECT RAISE(ABORT,'immutable source binding'); END;
            """)
            conn.execute("INSERT INTO core128_store_link VALUES(1,?)", (canonical(binding).decode(),))
            bindings.append(dict(binding=binding, state_digest=state_digest(conn, authority.limits)))
            # Objects created before enrollment receive a specific frozen epoch.
            store._core128_token = (binding, 1)
    return dict(generation=generation, stores=bindings)


def initial_state(anchor):
    if not anchor.get('generation') or not anchor.get('stores'):
        raise PublicationDenied("Missing frozen writer registration")
    state = {}
    for item in anchor['stores']:
        b = item['binding']
        if (b.get('schema') != 'aql.source-store-binding.v1' or b.get('writer') != WRITER
                or b.get('source') != anchor['source'] or b.get('source_path') != anchor['path']
                or b.get('generation') != anchor['generation'] or b['store'] in state):
            raise PublicationDenied("Invalid frozen source/store registration")
        state[b['store']] = dict(epoch=1, digest=item['state_digest'], pending=None, seen=set())
    return state


def apply_store_event(state, op, data):
    if not state or data.get('store') not in state:
        raise PublicationDenied("Unregistered store event")
    s = state[data['store']]
    if op == 'STORE_FENCE':
        if s['pending'] or type(data.get('epoch')) is not int or data['epoch'] != s['epoch'] + 1:
            raise PublicationDenied("Invalid store writer fence")
        s['epoch'] = data['epoch']
    elif op == 'STORE_INTENT':
        if (s['pending'] or type(data.get('epoch')) is not int or data['epoch'] != s['epoch']
                or data.get('writer') != WRITER or not isinstance(data.get('id'), str)
                or len(data['id']) != 32 or data['id'] in s['seen']):
            raise PublicationDenied("Invalid store denial intent/fence")
        candidate = MarketBar.from_dict(data['incoming'])
        if candidate.stable_key() != data.get('key') or digest(data['incoming']) != data.get('hash'):
            raise PublicationDenied("Store intent content mismatch")
        s['pending'] = data['id']
        s['seen'].add(data['id'])
    elif op == 'STORE_COMMIT':
        if (not s['pending'] or data.get('id') != s['pending'] or data.get('epoch') != s['epoch']
                or not isinstance(data.get('state_digest'), str) or len(data['state_digest']) != 64):
            raise PublicationDenied("Unproven store completion")
        s['digest'], s['pending'] = data['state_digest'], None
    else:
        raise PublicationDenied("Unsupported store operation")


def store_state(conn, anchor):
    state = initial_state(anchor)
    for row in conn.execute("SELECT body FROM core128_events ORDER BY seq"):
        event = json.loads(row[0])
        if event['op'].startswith('STORE_'):
            apply_store_event(state, event['op'], event['data'])
    return state


def verify_store(conn, binding):
    actual_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if str(Path(actual_path).resolve()) != binding['path'] or not has_binding(conn):
        raise PublicationDenied("Bound store path/identity replaced")
    row = conn.execute("SELECT body FROM core128_store_link WHERE singleton=1").fetchone()
    if row is None or row[0] != canonical(binding).decode():
        raise PublicationDenied("Bound store registration changed")


def verify_bindings(conn, anchor, *, pending_store_intent=None):
    state = store_state(conn, anchor)
    allowed = False
    for item in anchor['stores']:
        binding = item['binding']
        s = state[binding['store']]
        if s['pending']:
            if s['pending'] != pending_store_intent:
                raise PublicationDenied("Unresolved durable store denial intent")
            allowed = True
        with existing(binding['path']) as store:
            verify_store(store, binding)
            if state_digest(store, Limits(**anchor['limits'])) != s['digest']:
                raise PublicationDenied("Store changed outside registered authority or restored stale")
            source_blocked = {r[0] for r in conn.execute('SELECT stable_key FROM g1_integrity_events')}
            for row in store.execute('SELECT stable_key FROM g1_integrity_events'):
                if row[0] not in source_blocked:
                    raise PublicationDenied("Store quarantine missing authoritative source denial")
            for row in store.execute('SELECT symbol,interval,bar_open FROM market_bars'):
                key = f"{row[0]}:{row[1]}:{row[2]}"
                source = conn.execute('SELECT payload_json FROM journal_entries WHERE stable_key=?', (key,)).fetchone()
                if source is None:
                    raise PublicationDenied("Store row outside frozen source inventory")
                # Full state bytes are committed above; semantic agreement is a
                # separate invariant, not inferred from a matching hash alone.
                from ..storage.operational_store import OperationalStore
                retained = OperationalStore._original_bar(None, store, key)
                if content(retained) != content(MarketBar.from_dict(json.loads(source[0]))) and key not in source_blocked:
                    raise PublicationDenied("Store/source divergence lacks authoritative denial")
    if pending_store_intent is not None and not allowed:
        raise PublicationDenied("Missing durable store denial intent")


def load_token(conn):
    if not has_binding(conn):
        return None
    row = conn.execute("SELECT body FROM core128_store_link WHERE singleton=1").fetchone()
    if row is None:
        raise PublicationDenied("Missing store backlink")
    binding = json.loads(row[0])
    authority = bound_authority(binding)
    with authority._connection() as source:
        source.execute('BEGIN IMMEDIATE')
        authority._verify(source)
        epoch = store_state(source, authority.anchor)[binding['store']]['epoch']
    return binding, epoch


def bound_authority(binding):
    """Use only the explicitly registered backlink, never search paths/keys."""
    from ..journal.durable_journal import DurableJournal
    with existing(binding['source_path']) as conn:
        row = conn.execute("SELECT value FROM core128_meta WHERE singleton=1").fetchone()
        if row is None:
            raise PublicationDenied("Source registration missing")
        anchor = json.loads(row[0])
    if binding not in [i['binding'] for i in anchor.get('stores', [])]:
        raise PublicationDenied("Store not enrolled in source authority")
    # Do not run a journal constructor/migrate or create a missing bound source.
    journal = object.__new__(DurableJournal)
    journal.db_path = binding['source_path']
    authority = object.__new__(Authority)
    authority.journal, authority.anchor = journal, anchor
    authority.limits, authority.fault = Limits(**anchor['limits']), lambda _: None
    return authority


def deny_store_legacy(conn):
    if has_binding(conn):
        raise PublicationDenied("Bound store requires protected source reader; no legacy coverage/read")


def fence_store(authority, store):
    with authority._transaction() as conn:
        binding, _ = store._core128_token or (None, None)
        if binding not in [i['binding'] for i in authority.anchor['stores']]:
            raise PublicationDenied("Unregistered writer")
        epoch = store_state(conn, authority.anchor)[binding['store']]['epoch'] + 1
        _append(conn, 'STORE_FENCE', dict(store=binding['store'], epoch=epoch))
    # Caller must reopen the adapter to obtain the newly registered fence.
    return epoch


def write(store, incoming, *, force=False, original=None, event_options=None):
    token = store._core128_token
    if token is None:
        raise PublicationDenied("Unbound configured store writer")
    binding, epoch = token
    if str(Path(store.db_path).resolve()) != binding['path']:
        raise PublicationDenied("Store object path changed")
    authority = bound_authority(binding)
    operation = uuid.uuid4().hex
    with authority._transaction() as conn:
        s = store_state(conn, authority.anchor)[binding['store']]
        if s['epoch'] != epoch:
            raise PublicationDenied("Stale store writer fence")
        row = conn.execute("SELECT payload_json FROM journal_entries WHERE stable_key=?", (incoming.stable_key(),)).fetchone()
        if row is None:
            raise PublicationDenied("Store writer outside frozen source inventory")
        source_bar = MarketBar.from_dict(json.loads(row[0]))
        if not force:
            require_eligible_db(conn, incoming.stable_key())
        if force and event_options and event_options.get('kind') == 'CORRECTION_PROPOSAL':
            if original is None or content(source_bar) != content(original):
                raise PublicationDenied("Correction source binding mismatch")
        _append(conn, 'STORE_INTENT', dict(store=binding['store'], writer=WRITER, epoch=epoch,
                id=operation, key=incoming.stable_key(), incoming=incoming.to_dict(), hash=digest(incoming.to_dict())))
    store.binding_fault('after_intent')
    with authority._connection() as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            authority._verify(conn, pending_store_intent=operation)
            with existing(binding['path'], authority.limits.timeout_seconds) as target:
                verify_store(target, binding)
                target.execute('BEGIN IMMEDIATE')
                prior = store._original_bar(target, incoming.stable_key())
                alternative = incoming if content(incoming) != content(source_bar) else prior
                conflict = force or content(incoming) != content(source_bar) or (prior is not None and content(prior) != content(incoming))
                error = None
                if conflict:
                    alternative = alternative or incoming
                    evidence = record_event(conn, source_bar, alternative, **(event_options or {}))
                    # Source evidence and store evidence are separate transactions.
                    store_evidence = record_event(target, prior or source_bar, incoming, **(event_options or {}))
                    target.commit()
                    result = store_evidence['event_id']
                    if not force:
                        error = ContentConflictError(evidence)
                else:
                    target.rollback()
                    result = store._upsert_local(incoming, connection=target)
                store.binding_fault('after_store_commit')
                _append(conn, 'STORE_COMMIT', dict(store=binding['store'], epoch=epoch, id=operation,
                                                 state_digest=state_digest(target, authority.limits)))
                _project(conn)
                store.binding_fault('before_source_commit')
                conn.commit()
            if error:
                raise error
            return result
        except BaseException:
            conn.rollback()
            raise
