# GitHub Automation Roadmap
Status: DESIGN ONLY — automation runtime not deployed; issue-form templates are published on remote

Phase A (no AI agent credentials):
- PR checks: Python tests, format, lint, secret scan once code is present.
- Issue forms: bugs, work packages, proposals, questions.
- CODEOWNERS / branch protection configured after repository team identities are confirmed.
- Weekly summary generated from open Issues / PRs (GitHub Actions optional).
- Require linked issue and evidence for PRs.

Phase B (actual AI integrations):
- Determine whether ChatGPT and Claude can access this public repository through authorized connectors in their respective products.
- If not, build a dedicated broker service using GitHub App credentials and the approved AI provider APIs.
- Event intake: GitHub webhooks or polling; queue with idempotency keys and retry.
- Agent identities: separate bot accounts or GitHub App audit metadata.
- Scope: read issues/PRs, propose comments, create branches/PRs; no merges without owner.
- Enforce explicit human approval for costs, strategy promotions, deployment, live trading.
- Set API spending limits, per-issue reply cap, circuit breaker and logging.
- Never promise unattended action unless runtime and scheduling are actually deployed and verified.

Deployment acceptance:
- Verified end-to-end test: issue assigned to agent A -> comment from agent A -> response from agent B -> human approval -> linked PR.
- Logs include event IDs, actor, timestamps, costs and source commit.
- Kill switch stops agent actions.
