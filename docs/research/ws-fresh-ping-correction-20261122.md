# Fresh complete PING admission correction

## Original evidence and bounded conclusion

Owner executed fb86's reader comparison. Production reader upgraded101,
received4complete PING frames but returned only3matching local PONGs. The
first three PINGs were ~20seconds apart, with local PONG returns168/53/36ms
later. A new complete PING then arrived ~87.18seconds after the previous one;
its return path raised TimeoutError before recording a PONG return. StagePONG,
no underlying exception/OS code, max completed-frame gap71737ms.

The pinned quota rejects PONG if last_ping age>=60s. send_research_pong detects
exactly that otherwise-admissible condition and raises PONG_LIVENESS_EXPIRED.
Thus a NEW observed PING was refused because an OLD heartbeat was stale. The
comparison additionally lost that known context and labeled PONG_TERMINAL,
so reference reader was NOT RUN. Do not claim its outcome or infer that this
explains all seven earlier Windows10054 FRAME_READ resets.

Official Spot stream guidance requires promptly echoing a received PING's
payload. New receipt is evidence of current activity; a stale prior heartbeat
alone must not prohibit an otherwise legal immediate response.
https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md

## Narrow correction

The actual production parser records an internal one-use token ONLY for a
complete unmasked FIN PING with no RSV bits and<=125bytes, matching its returned
payload. The token binds the same connection and exact control bytes, has a
1second monotonic lifetime and is removed on use/new read. Partial/unknown
frames, copied/replayed/expired/mismatched tokens cannot refresh liveness.
No token preserves the prior conservative behavior; an invalid token fails.

A valid fresh token admits PONG in ONE existing quota transaction. Ban, missing
socket, clock regression,24h connection lifetime and the existing2messages/sec
half-budget remain enforced. Charge first, update observed heartbeat, then call
the original library PONG sender with unchanged bytes. Send failure remains an
error; local return does not establish server acknowledgment. No connection or
message cap is raised, no arbitrary heartbeat synthesized, no price/bar/data
validator changed. Ordinary text traffic does not create a PING token.

Reference diagnostic wraps its same connection so canonical auto-PONG uses the
same validated-token gate. Known PONG_LIVENESS_EXPIRED context is also preserved
if encountered without proof, rather than mislabeled as terminal.

Regressions recreate3regular PINGs then the actual87.18s delayed fourth through
BOTH real readers and require4matching local returns; complete an eight-bar
production-parser segment on one connection with this delay; retain ban, missing,
age and message-exhaustion refusal; test token one-use/expiry/connection/bytes/
framing. Existing12legacy tests remain. No real source run occurred in Work.

## One guarded install and original observation

ApplyPingCorrectionAndObserve is a manual, version-pinned correction for the
existing circuit HOLD. The caller must supply `ExpectedPreviousConfigSha256`
from the owner's read-only task/config diagnostic; the fresh Diagnose must
match that exact 64-character digest before any permit is created. This keeps
the installed config binding exact without assuming that a public historical
digest is still the owner's current config. It requires a fresh explicit
owner-local permit with `fresh_ping_correction`, existing valid continuous
authority, no active/uncertain execution, all prior gates/locks,
clock/task-policy readback and backups. Generic Apply cannot resume a circuit.

The existing rolling circuit must have NATURALLY expired before staging.
Its old outcomes and global rolling connection admission remain intact. No
circuit epoch/reset, counter deletion, quota raise or automatic HOLD clearance.
Prior authority bytes are retained in backup; a new config-bound grant and ONE
special initial ticket are committed. The existing scheduler alone validates
and archives the original HOLD under that ticket and starts the segment.
The observer waits for this specifically scoped initial circuit ticket; generic
or expired tickets do not disguise HOLD. Mode-selection regressions prevent
accidental execution of the separate old permit-repair branch.

The same local command observes the existing acceptance criteria:3completed
segments,24verified receipts,2normal rollovers, fresh progress and real fault
recovery. Historical gaps/receipts remain immutable. An operating report is
still required; no guarantee of external network stability or resolution of
all previous10054resets is implied. Orders/trading/PIT/G0/merge remain blocked;
330historical backfill is untouched.
