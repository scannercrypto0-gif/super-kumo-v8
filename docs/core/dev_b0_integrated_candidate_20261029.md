# Core DEV-B0 integration candidate — 2026-10-29

This candidate adds the previously separate Core174 research-only handoff and its dependency stack to the current Factory/Core DEV-B0 stack. Existing PR branches are unchanged and unmerged.

Pinned source candidates:
- Core174 handoff #177: 22ace3406810fd4110ae15f6b54195fe23841f8a
- Factory integrated engine/result bundle #185: 20928693f30b1730f0693a293bbf4a1f8ab21c88
- Core synthetic adapter #186: 7282e858598dd17309c80c384ec406a780f70e0b
- Factory input preflight current base used to prepare this candidate: 45a2919e9496cc5a9baa5a642ca1be9b46b6606b

The branch imports the Core174 dependency stack (PRs #155/#164/#170/#173/#177) as source files at the exact #177 head, then adds a narrow integration module:
1. Accept only the typed Factory research-data object and DATA_ONLY scope.
2. Bind archive and issued-receipt bytes to the handoff's committed digests.
3. Transform normalized OHLCV into engine input bars using explicitly hypothetical source-availability assumptions from the selected S00-S11 scenario.
4. Run Factory input preflight for the exact 2024-01-01 UTC, BTCUSDT 1m, 1,440-row window and 252-bar scoring warmup.
5. Return a prepared input packet only. It does not call replay, write results, or authorize study execution.

Synthetic integration tests exercise source handoff → input preflight → replay → local bundle, including a resolvable modeled trade, three independent paths, full opportunity denominators, costs and readback. All 12 scenarios are preflighted separately. Existing UNKNOWN and terminal-entry semantics are additionally covered by the exact-head Core/Factory suites in the same CI workflow.

## Trust and acceptance boundary

Synthetic tests do not prove original source custody, receipt issuer authenticity, point-in-time availability, profitability or actual historical results. The actual original ZIP and issued receipt must be presented to the integration candidate in the owner's authorized local environment and checked against pinned digests before any study. This ChatGPT session has no direct access to the owner's private local files, so it cannot claim that fresh local read happened here.

The study entry point remains unconditionally denied. No merge, OOS, PAPER, LIVE, PIT or G0 approval is implied. AIARC must independently review the exact integration HEAD, and the owner must separately issue the final one-run permit after the readiness packet is accepted.
