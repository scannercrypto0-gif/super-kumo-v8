# WS shared-path blocker: original two-reader result

Status: ORIGINAL_HOST_COMPARISON_FAILED; CONTINUOUS_OPERATION_NOT_ATTESTED.

Owner ran a626e1316860ff35f9e24d7c1b013fdb001270f3 against installed configuration 7c05de1aba8f11ced74373ac99819851297039cda6cd0e61dc1c4663c943c070. Original evidence directory identifier: network-compare-022bfc8cd25643009c0c19f36b4ca12e. HOLD preserved; service not restarted; task changes0; Core receipts0; orders0; trading NONE.

| Reader | Start ms | End ms | Result | PING / matching local PONG returns | Frames |
| --- | --- | --- | --- | --- | --- |
| production | 1795351619380 | 1795351754173 | FRAME_READ boundary underlying timeout | 2 / 2 | 24 |
| reference | 1795351754225 | 1795351866364 | FRAME_READ boundary reset10054 | 3 / 3 | 39 |

Production last complete frame1795351664106; two empty boundary polls then timeout after approximately90seconds without another complete frame. Reference last complete frame1795351826085; reset approximately40seconds later. No PONG-stage exception or WebSocket CLOSE was recorded. Native pong calls returned after64/29ms for production and27/30/34ms for reference. Local return is not remote server acknowledgement.

The reference exercises websocket-client1.9.2 control-frame receive logic but shares the same native library, TLS/socket transport, PONG quota gate, endpoint and host route. Both failures weaken a production-reader-only explanation; they do not exonerate the common software stack or identify Binance, ISP, router, Windows driver, or security filter as the actor. Sequential windows are not a controlled route comparison. No speculative transport change or increased reconnect budget is justified by this evidence.

## Concrete next operation requiring owner scope

Prepare a new, single-use host-trace permit, pinned to the configuration above, original HOLD digest, explicit owner decision and reviewed diagnostic commit. Existing per-configuration comparison claim stays untouched; do not delete/reuse it or reactivate the collector. This is a new diagnostic allowance, not renewal of continuous-operation authority.

- Run elevated on the original Windows host; preserve original service HOLD and all existing task/action/schedule/principal settings.
- At most two sequential diagnostic sockets, at most15minutes each, same approved endpoint/route/TLS and existing global2connections/rolling5minute admission. No REST/backfill, alternate endpoint/VPN, TLS bypass, or production task start.
- Pktmon trace scoped to approved endpoint addresses and TCP443; correlate the owned socket five-tuples with reader events. No unrestricted capture. Check existing trace/session/filter state first and refuse conflicting sessions; never stop another trace or clear its filters.
- Use bounded circular ETL, maximum64MiB and40minute watchdog, stop only the owned trace and remove only its uniquely named filters. Abort socket work if trace ownership, disk reserve or stop control cannot be proven.
- Keep truncated packet logging (maximum128bytes per captured packet) local. It contains network addresses and may include short TLS ciphertext fragments; it is not guaranteed to be headers only. Do not collect TLS session keys, decrypt application data, capture credentials or upload ETL automatically. Owner reviews any private evidence handoff separately.
- Record TCP reset direction/sequence context, retransmission/ACK progression, interface/drop indications and corresponding reader phase; preserve SHA256 manifests and cleanup result. Correlation narrows origin; a remote-address RST alone still cannot prove which upstream actor generated it.
- If administrator rights, trace ownership or bounded scope cannot be met, deliver that exact host blocker instead of substituting blind reconnects or changing policy.

Approval requested covers this exact bounded trace and new two-socket diagnostic allowance only. No trace, new connection, host configuration change or policy relaxation has been executed by Work. Implementation/OS validation of the approved trace runner is subsequent work; this document is a reviewable operational scope, not a tested trace executable.

Primary command references:
- https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start
- https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-filter-add
- https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2
