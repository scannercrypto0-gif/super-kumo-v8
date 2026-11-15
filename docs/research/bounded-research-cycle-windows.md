# Bounded offline research cycle on Windows

Use a Git checkout of this draft with the exact #286 commit
`d072544427d6b08473c88b2e36d5857cfd8581dc` available locally. If needed, run
`git fetch --no-tags origin refs/pull/286/head` from a checkout whose origin is
the ATLAS GitHub repository. The launcher itself uses local Git objects only.
Use Windows PowerShell or PowerShell 7 and an existing Python 3.11+ project
environment. Use a dedicated writable state directory and run one process per
state directory at a time.

From the draft checkout:

```powershell
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
$state = Join-Path $env:LOCALAPPDATA ('atlas-research-fixture-' + [guid]::NewGuid())
$plan = '723222e16af9f7524f0b09a6edf7a5b6156b4fead5e39256d41982d92abd042a'
powershell.exe -NoProfile -File .\tools\atlas_bounded_research_windows.ps1 -State $state -Python $python -ExpectedPlan $plan
```

To prove recovery, start with a fresh state path and add
`-InterruptAfterAck` to the first command. Exit code 73 means the second
G1 ACK was saved before its operational store and Scanner decision were
updated. Repeat the original command using the same state path. Expect four
ordered ACKs, three UNKNOWN and one NO_SIGNAL, with Factory
WAIT_AUTHENTICATED_PARENTS. A further invocation against that state should
print the same JSON. Result seals include a native per-store journal identity
and can differ on a fresh state directory. Keep the emitted JSON and the
state directory together to preserve the evidence.

The four bars are generated from the legacy synthetic NO_SIGNAL test recipe.
The simulated timestamps carry no publisher provenance. The JSON is a
bounded research report using the native Factory read-side census; the
fixture has no matching Discoverer or saved Lab lineage. Weekly Discoverer
reports remain available for their separate accepted fixture. Provider budget
is zero and the launcher does not enable orders, Secretary, Paper or PIT/OOS.
