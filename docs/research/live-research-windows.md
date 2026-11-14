# Operator-managed Windows research

Use the #271 draft checkout, Python 3.11+ with websocket-client 1.9.2, and local Git objects for #286 d072544427d6b08473c88b2e36d5857cfd8581dc and #305 0a45cb6de6027b6fba54320e07b0faf3317a5382. Use a new private NTFS state directory under a user-only ACL per sealed window. No scheduled task or reboot startup is installed.

## Administrator action

Install one trusted Python module in the operator's environment backed by the actual controlled route and aggregate shared-IP budget. The module must provide:

- read_verified_host(plan_pin, endpoint): fresh clock_checked_ms and clock_uncertainty_ms, plus verified source_rights_ref, region_ref and custody_ref.
- acquire_research_lease(**scope), renew_research_lease(lease_id, **scope), release_research_lease(lease_id, **scope): atomically reserve, renew and release against a shared ledger. Scope includes plan_pin, endpoint, state_path, connections, rest_requests and deadline_ms. Acquire and renew return lease_id, an identical scope, expires_ms (UTC milliseconds, at most 120 seconds ahead), and aggregate reserved_and_used and limit. Retain the same lease ID on renewal. The provider must reject conflicting leases across hosts, recover stale leases by expiry, preserve charged attempts across release, and enforce the declared deadline and actual provider limits. Keep calls synchronous and bounded by the remaining lease lifetime and perform no market requests from these authority methods.

No module or shared-IP capacity is bundled. The operator installs the real implementation and supplies its import name. Interface preflight checks compatibility; live acquires and revalidates an actual lease before opening the wire. Local state locking complements the external ledger.

## Operations

Run from the draft checkout in PowerShell. Set the authority module name to the installed provider and choose 2–96 bars in one finite window.

```powershell
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
$ctl = '.\tools\atlas_live_research_windows.ps1'
$state = Join-Path $env:LOCALAPPDATA 'atlas-research-qualified-window'
$bars = 4
$slot = [long]([Math]::Floor([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 900000) + 1) * 900000
& $ctl -Mode preflight -Python $python -AuthorityModule $trustedAuthorityModule
$plan = & $ctl -Mode plan -Python $python -Slot $slot -Bars $bars | ConvertFrom-Json
& $ctl -Mode live -Python $python -State $state -Slot $slot -Bars $bars -Pin $plan.sha256 -AuthorityModule $trustedAuthorityModule
```

Run status and stop from another shell, or recover after the writer exits:

```powershell
& $ctl -Mode status -Python $python -State $state
& $ctl -Mode stop -Python $python -State $state
& $ctl -Mode recover -Python $python -State $state -Pin $plan.sha256
```

A stop request closes the wire on the next loop checkpoint (frame wait at most 30 seconds, plus bounded authority latency). To resume an explicitly stopped window, use Mode rearm once the writer exits and repeat the same live command within its deadline. For a controlled restart test, add StopAfterFirst to the first live command and omit it on the second. The persisted connection budget is two attempts for the whole window, including any retry. A missed finalized slot stops the run. No REST or backfill is used.

The service keeps two rotating health logs and stops below 128 MiB free. Each isolated window keeps at most 96 sealed frames, its ACK journal and research SQLite stores. Archive or expire finished window directories according to the host retention policy. Status gives a native read-only Factory census and recent health metadata. Factory stays WAIT; there is no matching Discoverer or Lab lineage in this feed.
