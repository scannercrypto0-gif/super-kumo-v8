# Phase1 final technical acceptance — PR73

Owner final execution order, 2026-10-24. Review began at PR head
`2b78d5219a93df63936d793280baed29236a06f5`, tree
`a46162fc740e432a9cc8802f387b664adf747828`. Main at review start:
`4e4c3537036bdf2b106c1a63ec65b2a9855972a7`. Final published head and exact CI
links are recorded on PR73 / Issue71, avoiding a self-referential commit hash.
The review independently traced source, used disposable adversarial cases,
corrected defects and reran tests; previous green CI alone was not acceptance.

## Findings and disposition

| ID | Classification | Evidence, effect and disposition |
|---|---|---|
| A01 | FIXED | verify_backup checked journal/catalog SQLite integrity but not optional operational.sqlite. Injected corruption after SQLite backup and before inventory sealing: old create_backup and restore_backup both accepted3 records despite unreadable hot SQLite. Now all included SQLite snapshots receive integrity_check; regression refuses sealing, preserves original3 journal rows and does not update last_backup_ms. |
| A02 | FIXED | Old os.walk accepted an unlisted empty directory, materialized arbitrarily large directory listings and omitted traversal deadline checks. Verification now streams scandir, checks deadline, rejects unlisted directories/files, bounds depth16, and refuses nonregular files before opening. Real FIFO on POSIX; file-type metadata simulation on Windows. These controls do not promise preemption of a blocked kernel I/O call. |
| A03 | FIXED | parse_constant rejected NaN/Infinity literals but JSON1e400 became float infinity. finite parse_float rejects positive/negative exponent overflow. Valid canonical output/hashes do not change. No false claim of an exploitable archived-bar corruption bypass: existing envelope numeric checks already rejected such values downstream. |
| A04 | ACCEPTED LIMITATION | Windows file fsync and process-termination/restart are tested. Portable directory fsync remains unsupported; health explicitly DEGRADED. Power loss, hardware/controller cache, real full-disk and full ACL enforcement are not certified. |
| A05 | ACCEPTED LIMITATION | Private root/parent ACLs and separately retained expected commitments are required. Hashes detect changes relative to retained anchors, not a privileged rewrite of all files/anchors. Heartbeat validates current source anchor, not every earlier segment on every call; backup/restore performs full reconciliation. |
| A06 | ACCEPTED LIMITATION | Journal/catalog/hot snapshots are individually coherent, not one global transaction; source may advance during capture. Hot store is rebuildable and may lag. Real termination during backup/restore leaves partial attempts; retry verifies a fresh attempt without primary loss. |
| A07 | ACCEPTED LIMITATION | Archive is opt-in/unwired; bounded wake-ups, separate catalog ACK and source read-only access preserve existing pipeline/remote semantics. Blocked archive and blocked backup tests permit new core commits. Host CPU/I/O/disk remain shared, not hard-isolated; actual host disk exhaustion can still stop ingestion. |
| A08 | ACCEPTED LIMITATION | Full recorded envelope hashes cover original receipt/commit metadata, with unknown availability/source-event/fsync times null and a clearly derived lower bound. No runtime trader-decision capture or confirmed PIT availability is claimed. |
| A09 | OWNER DECISION | Disk/capture horizon, independent backup media/location, encryption/access, RPO/RTO, final ADR, activation and merge approval. None is automatically provisioned or authorized; code can be reviewed/merged only as inactive optional Phase1. |
| A10 | FUTURE PHASE | Larger/incremental backups, measured compression/Parquet and cloud projections. JSONL is suitable for this tested bounded Phase1 slice; Parquet is not imposed as a current requirement. No pruning/production/cloud work. |

No unresolved confirmed data-integrity blocker remains in the reviewed bounded
code after these corrections and the required final cross-platform acceptance.
Recommendation applies to **optional, inactive Phase1 code**, not production,
large-volume backup service, cloud or live activation. Final CI must be green
at the exact published source before owner merge approval.

## Acceptance coverage

60 Phase1 tests (48 original +12 new cases) cover canonical encoding and finite
JSON, full envelope/source reconciliation, sealed payload/manifest hashes,
transactional intent/index/watermark, exact duplicates/conflicts, gap/order
reporting, journal identity/rollback/anchor tampering, all write/rename/ACK fault
boundaries, real os._exit termination, locks, bounded queue and disk reserve,
injected ENOSPC/EACCES, WAL snapshots, intact/corrupt/missing-file restore,
independent expected-digest mismatch, new-directory restore, and restart retry.
Actual device failure, privileged races and hardware power loss are not covered.

Python3.14.3 / pytest9.1.1 / pytest-timeout2.4.0 on Windows11:
`tests/test_g1_storage_02.py -q -rs --tb=short`: **60 passed in32.33s, zero skips**.
Applicable unchanged G1 suite and final exact-head Ubuntu/Windows CI outcomes are
reported on Issue71; ordinary intentional external/SIGKILL skips remain explicit.
The existing G1 pull-request workflow checks GitHub's synthetic merge with main;
that commit is a test artifact, never an authorized repository merge.

## Larger actual disposable measurement

Command: `python -B scripts/measure_g1_storage_02.py --rows 4096`.
Windows11 build22000, Python3.14.3, UTC2026-10-24T11:04:19.840823Z.
Synthetic8 symbols,1m, no compression/live traffic. No other local test suite
ran concurrently with the measured operation. This is not a controlled host
benchmark or an SLA. Temporary databases/copies were cleaned by TemporaryDirectory;
the inventory digest below identifies the drill, not an available offsite copy.

| Measurement | Actual |
|---|---:|
| Records / sealed segments |4096 /64 |
| JSONL bytes |4,507,946 |
| Manifest bytes |141,378 |
| Catalog bytes incl allocation |831,488 |
| Journal snapshot bytes |2,560,000 |
| Archive bytes/row incl catalog/manifests |1,338.0888671875 |
| Archive duration |13.0065s |
| Verified backup / restore |9.2705s /9.8016s |
| Inventory files / bytes (inventory itself excluded) |130 /8,040,812 |
| Reconciled restored archive/source rows/watermark |4096 /4096 /4096 |
| Initial core commit median /p95 |26.1467ms /65.1001ms |
|20 core commits during blocked archive: median/p95/max |14.9306 /25.7000 /33.4700ms |

Retained inventory digest:
`a5d646c96e73cddc86536b5e35fb66539d6ef9273b2f86eeba484946c0ad2b29`.
Off-device protection: **NOT_VERIFIED**. This fresh4096-row sample supplements,
not retroactively replaces, the older512-row measurement at the prior source.

Exact measured source-file SHA256 values (match corrected source):

| File | SHA256 |
|---|---|
|contracts.py|7c4f8f14fef21ef419b02960bf217033fe9787249f64c2a57581ab40bb51cdef|
|local.py|a899071bc0c0db4301d22c3412acb5d4b14a284d519eaba96d51e4a06efbec23|
|backup.py|d4d9437d78e6b2963df278005f5c15ea7f079fea5e5c172b50312101bca1d03d|

### Extrapolation, not measured capacity

DecimalGB = symbols*1440*days*1338.0888671875/1e9:

| Scenario |30d GB|90d GB|365d GB|
|---|---:|---:|---:|
|10 symbols|0.5781|1.7342|7.0330|
|100 symbols|5.7805|17.3416|70.3300|
|500 symbols|28.9027|86.7082|351.6498|

Exclude journal/hot/PIT/research/WAL/partials/backups. Adding #67's separate
257.27GB/year journal+hot extrapolation to the high archive scenario gives about
608.92GB primary/year before richer context data; two full copies total about
1.22TB, three1.83TB across devices. These assumptions are not disk authorization.

Default10GB is an archive reserve, not a protected host quota. Backups also
consume disk and require explicit destination capacity planning; shared-volume
write pressure is not isolated. Defaults8192 inventory files,2GB and60s are
fail-closed bounds, **not a promise to back up a growing year-long dataset**.
At default64 rows/segment, two files/segment +2 SQLite snapshots permit at most
4095 segments /262,080 rows before the file cap, even if byte/time limits allow.
That is approximately18.2/1.82/0.364 days at10/100/500 one-minute symbols;
short partitions/runs or an extra hot snapshot reduce it. Time/byte ceilings can
bind earlier. Larger/incremental scopes need explicit measured budgets in a
future phase, not silent unlimited settings. Partial attempts are retained and
need separately authorized cleanup. No linear timing extrapolation is certified.
