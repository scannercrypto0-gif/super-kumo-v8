# Read-loop comparison after actual circuit opening

Last actual owner output is HELD, not continuous-operating success. The retained
outage evidence contains seven Windows10054 receive resets and one underlying
boundary read timeout, across four two-attempt segments; only two verified
research receipts, zero completed segments/rollovers. Reset lifetimes were
77.7–840.8seconds. All eight failures were FRAME_READ/FRAME_BOUNDARY and eligible;
there was no reported handshake/TLS/PONG/quota/data/partial-frame failure.

Microsoft defines10054 as connection reset by peer. This does not identify
Binance versus an intervening network/filter/shared client stack. The current
evidence does not retain successful Ping/Pong timing, so it cannot establish
whether a server heartbeat deadline, local read-loop issue or another reset
cause was involved. No further production patch or circuit-limit increase is
justified by the error number alone.

## One manually invoked, bounded diagnostic

`ATLAS-WS-NETWORK-COMPARE.ps1` opens **at most TWO sequential connections** on
the SAME approved BTCUSDT15m endpoint, for at most15minutes each. This duration
covers the longest observed14-minute failure lifetime; it is not a sustained
operational acceptance period. Execution is owner-local/explicitly invoked,
not an automatic retry of the held service. No source calls were made in Work.

Production reader uses the actual read_research_frame/manual PONG path.
Reference uses websocket-client1.9.2 recv_data_frame(control_frame=True), which
replies to PING through the canonical library. Both keep the SAME pinned
connection factory, TLS validation, frame parser, quota/PONG gates, bounds and
route. Thus this isolates the read/control loop; it is NOT an independent TLS
or OS implementation. No endpoint, transport security, proxy, DNS or firewall
setting is changed.

It requires Ready/circuit HOLD, exact known config/runtime pins, existing valid
continuous permission, no active/pending/incomplete collector and both existing
locks. It checks the prior quota's ban/pending/socket/backoff state and charges
shared persistent2/5min admission before either attempt. A create-once claim
prevents repeating the same comparison on this baseline. The service stays
HOLD; no task schedule/action/principal change, initial-ticket reissue or
service restart is performed. Terminal ban/auth/protocol/clock/unknown failure
prevents the second connection. The parent process has a40minute ceiling.

Only bounded counters/events are retained: complete-frame timing, incoming
PING payload length/hash, local PONG-return time and exact echo match, close
code, fault phase/classification/OS codes. No market payload, price, bar, Core
receipt, API credential or host-address dump is retained. A local PONG return
is NOT a server acknowledgment. Partial frames stop; empty boundary polls have
the existing90second ceiling. All data are discarded, not admitted downstream.

Results live in a unique private network-compare directory with a plan and
per-reader results, plus comparison.json. Verdicts deliberately avoid false
causality: both healthy windows leave intermittent/pipeline cause UNPROVEN;
a difference is an observation subject to sequential-window confounding;
both interruptions implicate the shared stack/path and require host network
trace to identify the reset actor. No automatic source switch/library rewrite
or ongoing-operation approval follows any result.

## Evidence and boundaries

Offline regressions replay actual unmasked server frames through both actual
readers, decode the actual outbound masked PONG and check exact echo bytes,
prevent network access, test partial/empty-frame timeouts, state/budget refusal,
redaction and terminal gates. Synthetic results never count as owner operation.

References:
- https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2
- https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md

Orders/trading/PIT/G0 remain blocked; the existing historical330 backfill and
retained source data are untouched. Final continuous-operation status remains
NOT_ATTESTED. This is one focused root-cause experiment, not another blind
production restart or a claim that Windows10054 alone establishes its author.
