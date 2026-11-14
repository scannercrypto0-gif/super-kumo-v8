# Windows bounded live research

Use the #271 draft checkout, Python 3.11+ with websocket-client 1.9.2, and local Git objects for #286 d072544427d6b08473c88b2e36d5857cfd8581dc and #305 0a45cb6de6027b6fba54320e07b0faf3317a5382. Select a future UTC 15-minute boundary as Unix milliseconds. Use a private dedicated NTFS state directory.

```powershell
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
$state = Join-Path $env:LOCALAPPDATA 'atlas-two-bar-proof'
$slot = [long]([Math]::Floor([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 900000) + 1) * 900000
$plan = & powershell.exe -NoProfile -File .\tools\atlas_live_research_windows.ps1 -Mode plan -Python $python -Slot $slot | ConvertFrom-Json
```

Before arming the run, the operator-installed trusted authority module must provide the three callable interfaces in the runner. It must verify lawful source/region, private custody and fresh clock qualification, authenticate a current shared-egress reservation for the plan and endpoint, and verify that the reservation covers this state directory, at most two connections, zero REST and the full window. No authority module or verified budget is provided by this draft. The earlier one-shot waiver does not apply. Install the authority module only in the trusted Python environment.

Invoke the following at the selected boundary. The launcher stages pinned files before entering the observation process, so start it ahead of time using the command below. It enforces a 35-minute absolute window and exits after two consecutive finalized bars or a terminal stop. Ctrl+C stops the foreground run. Use `-Mode status` for native read-only census or `-Mode recover -Pin $plan.sha256` for offline reconstruction in the same state directory after stopping the writer. Neither mode reconnects.

```powershell
& powershell.exe -NoProfile -File .\tools\atlas_live_research_windows.ps1 -Mode live -Python $python -State $state -Slot $slot -Pin $plan.sha256 -AuthorityModule $trustedAuthorityModule
```

Keep local health.jsonl and the sealed raw receipts private. The upstream market-data stream is the single public BTCUSDT Spot 15m endpoint. Missing closes fail closed, without historical REST recovery. Factory output is a research census with admission WAIT; no matching Discoverer/Lab lineage is asserted.
