# WP-R11 — External Custody Contract (no external service connected)

This prototype establishes an interface to an owner-approved, separately controlled, immutable checkpoint service. No actual network client or provider was configured, no secrets used, and no cloud-side object, bucket, account, ACL, role, policy, or retention rule was created.

## Security invariants

1. `CustodyPolicy.external_independence_verified` must be true before attempted publication or verification. **This Boolean is caller-supplied; it does not prove independence**. A later adapter must carry independently audited authorization and custody evidence.
2. `put_once(key, bytes)` MUST be atomic and non-overwriting under concurrent callers, including after crashes and retries. A real adapter must provide independently verified write-once retention, separate identities, no-delete protections, and constrained owner/auditor read authority.
3. Checkpoint keys bind namespace, owner, complete trial family, sequence and exact head digest. Read-after-write must match the exact canonical bytes. A missing or changed record is an error.
4. Failures remain failures; do not claim storage or a trust receipt if remote acknowledgment or exact read-back fails. A retry uses the same content-addressed key and requires exact-byte idempotency.
5. `verify_stored_checkpoint` checks the externally read exact bytes and pins the journal's on-disk validated historical prefix. It does **not** attest who wrote the remote bytes.
6. Hashes cannot prevent hostile rewriting of both the research journal and an external store under a shared principal. Owner acceptance requires **out-of-band external authorization** and audit evidence.

## Mandatory preflight before any live external adapter

- Owner expressly approves provider, account, region, spend limits, retention term, separation of credentials and failure handling.
- Verify adapter conditional create atomicity, read-after-write semantics, object version retention, deletion lock, IAM separation, audit logs, access-time proof and incident playbook.
- External key/namespace must not be supplied from untrusted dynamic path segments; adapter must prevent traversal/encoding ambiguity.
- Run platform integration tests for outage, conflicting concurrent writes, rollback, partial read, owner-key compromise, retention expiry and Windows power loss.
- Retain external anchor receipt and audit proof independently from any mutable research repository.

Until those gates pass: **no external custody has been established**. The fake store in tests is an in-memory protocol test double, not evidence of actual independence. WP-R6/7 confirmation stays fail-closed, no strategy nomination/trading authorization, G0 remains OPEN.
