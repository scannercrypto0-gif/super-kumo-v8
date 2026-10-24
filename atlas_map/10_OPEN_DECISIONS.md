# ATLAS Quant Lab — Open Architectural Decisions
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## Decision Format
Each decision lists: objective, context, options (A/B/C), trade-offs, and recommendation.
All decisions require **owner approval** before implementation.

---

## OD-01: `manifest_integrity_hash` — Instance vs. Content Determinism

**Objective:** Clarify whether `manifest_integrity_hash` should be deterministic across library instances.

**Context:** Currently includes `created_at_ms` (wall-clock at validate_bars time), making it non-deterministic across instances or processes running on different machines or at different times.

**Impact:** Cannot use this hash to verify that two researchers processed the same dataset identically across separate runs. The audit trail for multi-researcher reproducibility is weakened.

**Options:**
- **A — Keep as-is:** Document the instance-scope limitation explicitly. The hash serves as an instance fingerprint, not a cross-instance reproducibility guarantee.
- **B — Add `content_hash`:** Keep `manifest_integrity_hash` (instance fingerprint), add a separate `content_hash` = deterministic hash of bar content only. Both hashes serve different purposes.
- **C — Make fully deterministic:** Remove `created_at_ms` from the hash; rename to `content_hash`.

**Trade-offs:**
- A: Zero code change; limits reproducibility verification.
- B: Dual-hash adds clarity at the cost of schema complexity.
- C: Breaks existing API contracts (field rename); requires test updates.

**Recommendation:** B — Add `content_hash` alongside the existing hash. Preserves backward compatibility.

**Status:** AWAITING OWNER DECISION | **Related Issue:** #76

---

## OD-02: Shared Indicator Box Ownership (G1-ARCH-21–44)

**Objective:** Clarify whether the Shared Indicator Box (G1-ARCH-21–44) belongs to Strategy Factory (C) or is a separate sub-system between Secretariat (G) and Traders (I).

**Context:** The indicator box as designed in `01_CONTRACT.md` (G1-ARCH-21–44) seems to serve two purposes: (1) indicator computation for research (Strategy Factory role), and (2) live indicator streaming for the Secretariat/Scanner/Traders workflow. These have different lifecycle, consistency, and latency requirements.

**Options:**
- **A — Single box, dual purpose:** One Shared Indicator Box serves both research (batch PIT) and live trading (streaming). Strict API boundaries prevent contamination.
- **B — Two separate boxes:** Research Indicator Box (inside Strategy Factory, PIT-correct, batch) and Live Indicator Box (inside Secretariat, streaming, eventual).
- **C — Defer:** Keep current design (one box); split only when demand is proven.

**Trade-offs:**
- A: Simple; risk of research PIT leaking into live path or vice versa.
- B: Clean separation; doubles implementation effort.
- C: Avoids premature optimization.

**Recommendation:** C for now — defer until Secretariat is implemented. Flag as a split decision point when G2 work begins.

**Status:** AWAITING OWNER DECISION

---

## OD-03: Operational Store → Historical Library Bridge Design

**Objective:** Define how live-collected bars flow from the G1 Operational Store into the Historical Library for research use.

**Context:** Currently the two are completely isolated (dep_guard enforces this). Research data must be imported manually. Issue #71 covers Phase 1 archiving but doesn't define the bridge protocol.

**Options:**
- **A — CLI export tool:** A standalone script that reads the operational store and imports into the historical library. Triggered manually by the owner.
- **B — Automated nightly job:** A scheduled process that exports new bars daily into the historical library.
- **C — Event-driven bridge:** Each finalized bar in the operational store triggers an append to the historical library in near-real-time.

**Trade-offs:**
- A: Simple, owner-controlled, no new architecture. Manual effort.
- B: Automation; risk of partial-bar import if job runs mid-session.
- C: Complex; PIT correctness harder to guarantee in real-time.

**Recommendation:** A for G2; upgrade to B when operational data volume justifies automation.

**Status:** AWAITING OWNER DECISION

---

## OD-04: Asset Intelligence Lab (E) — Standalone vs. Strategy Factory Sub-Lab

**Objective:** Decide whether the Asset Intelligence Lab (Issue #72) is an independent department or a sub-component of the Strategy Factory.

**Context:** Issue #72 proposes BTC/PAXG specialist outlooks. The outputs (AssetOutlook) are read-only and informational. The question is whether this justifies a separate department with its own code boundary or can be implemented as a factory extension.

**Options:**
- **A — Sub-lab of Strategy Factory:** Implement as `research_wp_r0/asset_intelligence/`. Shares the PIT-correct accessor and indicator library. No new department boundary.
- **B — Standalone department:** Own code directory, own interfaces. Can evolve independently.

**Trade-offs:**
- A: Less overhead; natural integration with existing research lane.
- B: Cleaner separation if AIL grows to consume live signals or external data.

**Recommendation:** A — Start as a Factory sub-lab. Promote to standalone only if it needs live data access (which would require its own boundary).

**Status:** AWAITING OWNER DECISION

---

## OD-05: Market Intelligence (J) vs. Asset Intelligence Lab (E) Boundary

**Objective:** Define the boundary between Market Intelligence (broad market signals) and Asset Intelligence Lab (deep per-asset analysis).

**Context:** Both departments touch BTC. Market Intelligence focuses on market-wide context (BTC dominance, ETH/BTC ratio, altseason). Asset Intelligence Lab produces deep specialist outlooks for specific assets.

**Options:**
- **A — Strict separation:** MI covers only cross-market ratios and breadth; AIL covers individual-asset deep analysis. BTC appears in both but at different levels.
- **B — AIL subsumes MI:** One department covers all intelligence (broad + deep). Simpler.
- **C — Defer:** Both are L0 concepts; define boundary only when one begins implementation.

**Recommendation:** C — Defer until one department reaches implementation stage. The current distinction is adequate for documentation.

**Status:** AWAITING OWNER DECISION (deferred to G5)

---

## OD-06: `WritePriority` — Wire into Pipeline or Remove (Issue #75)

**Objective:** Decide whether `WritePriority` (designed in `lanes.py`) should be connected in `pipeline.py`.

**Context:** `WritePriority` exists in `lanes.py` but is not wired into `pipeline.py`. It's designed to give core ingestion commits priority over background SQLite writes. Under low single-symbol load, it may be unnecessary.

**Options:**
- **A — Wire it in:** Connect `WritePriority` in pipeline. Correct under high concurrency.
- **B — Remove it:** It adds complexity without proven need at current scale.
- **C — Keep as is:** Leave it in `lanes.py` unconnected; wire when multi-symbol scale is needed.

**Recommendation:** C — Keep unconnected until SC-03 (multi-symbol) is approached.

**Status:** AWAITING OWNER DECISION

---

## OD-07: Supabase Tier Selection

**Objective:** Decide which Supabase tier to use based on expected data volume.

**Context:** At 10 symbols × 1m interval, data grows ~3.6MB/day. Supabase Free tier (500MB) would be exhausted in ~4.2 months. Issue #67 tracks this decision.

**Options:**
- **A — Supabase Free:** Acceptable for proof-of-concept / first 4 months.
- **B — Supabase Pro ($25/month):** 8GB storage, suitable for long-term single-cluster use.
- **C — Self-hosted PostgreSQL:** Full control, no recurring cost, but DevOps overhead.

**Recommendation:** Start with A for proof-of-concept; upgrade to B when proof-of-concept validates the approach.

**Status:** AWAITING OWNER DECISION (Issue #67)
