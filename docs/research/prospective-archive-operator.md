# ATLAS prospective observation and April archive

Package PKG-PROSPECTIVE-OBSERVATION-PLUS-ARCHIVE-01. Research only. Install this
checkout on a persistent host with a synchronized UTC clock, outbound public
Binance Vision WebSocket over TLS, and a dedicated private volume. Use a clean
state directory on a non-original volume. Keep SQLite DBs and health records
private. Use a supervisor with restart-on-failure and the same state directory;
the runner takes an OS-backed SQLite single-writer lock. The supervisor should
stop after the intended evidence window. The runner bounds the session to four
days and total storage to 672 finalized 15-minute bars.

    python -m pip install -e .
    python -m tools.atlas_prospective_observe --state /private/atlas-p0 --public-observation
    python -m tools.atlas_prospective_observe --state /private/atlas-p0 --status

On Windows substitute a separate non-E: path. A failure before connecting exits
nonzero; a successful connection does not attest a finalized bar. Review
health.jsonl and read-only Factory counts. No API credentials are used.
A restarted collector replays existing journal and store receipts. A missed
decision outside the freshness limit becomes UNKNOWN rather than a backdated
signal. Quarantined input or outcome bars invalidate their verified views.
An event is visible only after its recorded UTC time. A horizon requires a
subsequently finalized eligible bar and its actual COMMIT-return receipt;
a delayed bar or skipped interval yields an explicit late or missing state.
A synthetic clock advance cannot establish operational elapsed time.
The checked-in strategy is an engineering fixture, with no research merit claim.

April intake uses a distinct private directory. Use only for the documented
personal, noncommercial and non-production scope of Binance Vision Dataset
Terms v1.0. The command downloads only the named partition and adjacent
checksum; it pins the publisher URLs and refuses redirects. Keep source bytes
and any price-bearing receipts out of GitHub.

    python -m tools.atlas_april_archive --state /private/atlas-p1 --p0-state /private/atlas-p0 --personal-noncommercial

The P1 CLI conservatively pauses while P0 holds its runner lock, checking
before and during network acquisition, before admission, and between Core
checkpoint and index batches. The index transaction rolls back if paused.
Use different volumes to further reduce I/O contention. Retry the same command to reuse verified
capture checkpoints and existing Core staging. On conflict preserve the
existing generation and the quarantined capture. A verified new publisher
revision must enter an explicitly selected new Core generation with a parent
source hash; the default CLI does not overwrite or automatically select a
revision. Core245 and Core253 remain distinct and are checked against identical
source/manifest and bar contents. Historical issuer known-at remains unknown.

The focused CI uses locally generated fixture data only. No broker, order,
Paper, Secretary enqueue/ACK, G0 or original March replay is part of either
command. Rollback before merge is closing the draft. On a deployed host stop
the observer and retain the isolated evidence for readback.
