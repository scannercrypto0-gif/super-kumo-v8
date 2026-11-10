# CODEX-PKG-04 — offline consumer v1

Project AQL-CRYPTO-RESEARCH-001. **BLOCKED_ONE_EXACT_SEAM**:
`PERSISTED_DISCOVERER_FACTORY_JOIN_NOT_AVAILABLE`.

Working bounded slice: persisted actual repository-generated synthetic finalized
source/Scanner decision census → G2 pending horizons → G3 modeled state.
The reader is standard-library-only and executes no producer, opens no database,
calls no network, and creates only a new explicitly named output file. It does not
rebuild an engine, registry, observer, or acknowledgment workflow.

From repository root, offline (Python >=3.11):

```powershell
$anchor = (Get-Content tools/research_evidence_gateway/fixtures/manifest.sha256).Trim()
python -B -m tools.research_evidence_gateway.gateway --inputs tools/research_evidence_gateway/fixtures --manifest-sha256 $anchor --output gateway-new.json
python -B -m pytest tools/research_evidence_gateway -q --basetemp=work/gateway-tests
```

POSIX equivalent:

```sh
python -B -m tools.research_evidence_gateway.gateway --inputs tools/research_evidence_gateway/fixtures --manifest-sha256 "$(cat tools/research_evidence_gateway/fixtures/manifest.sha256)" --output gateway-new.json
python -B -m pytest tools/research_evidence_gateway -q --basetemp=work/gateway-tests
```

Output must not exist or be inside the input directory. CLI exit 0 means the
bounded read/export succeeded; inspect JSON `status` for package acceptance.
Invalid inputs exit 2 without output. Canonical JSON is sorted, compact, ASCII,
finite numbers only. `sha256` hashes the canonical body excluding that field;
the final newline is excluded. Input anchors hash canonical JSON, so checkout
line endings cannot change integrity. Retain the manifest digest independently;
editing the manifest and its digest together is **not** publisher authentication.

## Existing evidence and exact reuse

`fixtures/source.json` and `fixtures/results.json` were captured on 2026-11-10
from **the existing test**, unmodified:
`tests/paper_sim/test_upstream_integration.py::test_real_pinned_observer_scanner_read_to_offline_simulator`
at G3 PR #288 `0ca716eaf1b8ae1a66ed6f3fbcec34f22c73ced7`.
Only its adapter invocation and simulator return values were intercepted to save
the already produced JSON. Its assertions passed, including actual Scanner,
native journal/OperationalStore, G2 verified reader, simulator durable replay,
and SQLite before/after equality. No G4 accepted test was rerun.

The existing test independently verifies the two imported upstream files from
G1 PR #286 `d072544427d6b08473c88b2e36d5857cfd8581dc`:

| File | SHA256 of Git bytes |
| --- | --- |
| `src/aql/observation/prospective.py` | `3a72abcdf54d5186736562534e0402dfd18dc465981781edc7c0b4404fdf6fa7` |
| `src/aql/observation/durable_bridge_v1.py` | `7a97c1d51e74d088d5dacaab604794005c12dc5a1d58a8b1542b794c7993f3b7` |

Four decision slots contain three UNKNOWN warmup/gap decisions and one ENTRY;
the ENTRY has three pending horizons. One modeled result has two assumed taker
fills. These are synthetic values, never venue fills. The random journal ID is
retained as generated; fresh-process replay uses the same persisted bytes.

The manifest records current main and all relevant open draft heads observed at
intake. Branch is based on main `90af9794880cbeb00e7e974bfa906ff5e9666183`;
no whole historical PR is included or merged. Only this new namespace and its
new dedicated workflow are changed.

Existing readers inspected and reused as contract references:
G3 `adapter.signals_from_prospective`, G1 `ProspectiveObserver.verified_read`,
G2 `secretary_g2_readonly_v1.consume_verified_opportunity`, Factory E
`read_experiment` and Discoverer `g4_factory_acceptance_seam`.
The Secretary reader has a different native schema; it is not substituted for
the prospective reader. Factory's existing reader opens its DB via its own
connection helper, so this gateway does not invoke it against upstream stores.
No duplicate registry or producer business validation is implemented.

## One exact seam and owner

Inspected current Factory #267 `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf`
and Discoverer #276 `c568e3b281795f9eef2165c0e6f571b87157a23c` Git trees.
Their G4 test constructs an ephemeral actual Factory registry; the inspected
trees contain no persisted candidate proposal/checkpoint + Factory experiment
readback + join receipt + H trial population for this gateway to consume.
No accepted G4 fixture is rerun merely to manufacture missing input.

Integration #271 owns the handoff, with Discoverer/Factory contract owners:
supply a sanitized already-produced synthetic evidence bundle with independently
retained digests and exact native versions. The current verified native contracts
include `aql.factory.e.research-experiment.v1` and
`aql.g4.discoverer.factory-existing-registry-join.v1`. The existing join explicitly
reports comparison trials/paired results `NOT_PERFORMED`; its three generation
attempts cannot stand in for ten H variants. This implementation deliberately
does not claim its missing research adapter or missing-trial rejection is tested.
Research attempt/trial/variant counts stay null, not zero and not Scanner slots.
That one absent persisted research chain prevents full Package 04 PASS.

## Tests and boundaries

Positive: existing native synthetic chain; canonical export; four decision slots;
UNKNOWN retained; pending horizons; missing horizons explicitly NOT_AVAILABLE.
Negative: missing/duplicate modeled result, duplicate decision, source/config/
strategy/evaluator/engine swap, parent mismatch, mixed UTC as-of, fake ACK,
real-fill claim, fabricated maturity, UNKNOWN PnL, NO_FILL with fills, NON_PIT
promotion, duplicate JSON key, corrupt/truncated/nonfinite JSON, changed manifest
anchor, output overwrite and output in input directory. Two subprocesses must
produce byte-identical output; input bytes must remain unchanged.

Missing rights/known-at do not become verified rights/PIT: both remain
NOT_ATTESTABLE. Mature/missing native observations are currently rejected with
`UNSUPPORTED_MATURE_EVIDENCE_CONTRACT`, not silently upgraded. Synthetic embargo
does not mean elapsed natural horizon maturity. No independent publisher custody,
real OOS, alpha, official stage signoff, G0, paper/live authority, or real data
operation is claimed. The independently checked grade applies only to bytes and
bounded synthetic lineage, not scientific acceptance or independent Audit.

## Governance readback

Read PM OS #205/6721828613 and amendments /6721846844 and /6741235513,
canonical #202, current relevant role records, and PKG01/02/03 dispatch
#271/6768334518. Latest accessible actual owner-host G2 handoff remains
#271/6764652288: 29 decisions (16 ENTRY, 13 UNKNOWN), no matured horizon count;
owner-reported host bytes were not inspected. Later synthetic engineering
#271/6767096389, scoped Audit /6767647980 and real-admission block /6768196303
remain distinct. Current user instruction explicitly launches PKG04 only.
Private chats/E: are inaccessible and not claimed reviewed. G2 is untouched.
