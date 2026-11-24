# Original permit-byte repair

Owner deployed d582 successfully with continuous_research=true, config SHA256
857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2,
authorization SHA256
562300683daa9cd3640a4be63ab96a5c71a3d9e4d70a9d64f419e1d84aa5f576.
The observer refused CONTINUITY_OWNER_PERMIT_PIN. This is a demonstrated
implementation bug, not evidence that the source owner changed or the network
failed: gate named the claimed permit with SHA256(original raw bytes), but
saved canonical(auth) at that name. PowerShell JSON key order/whitespace/UTF8
is not canonical Python JSON. Earlier generated gate inputs were canonical,
which missed this seam. Regression now uses noncanonical Unicode original
bytes through the actual gate and subsequent authority validation.

Future gate claims preserve the exact authenticated bytes; parsing uses the
same byte snapshot, and a changed file before claim fails closed. No pin
validator is relaxed, no digest renamed and no original source reconstructed.

The already installed runtime does not need redeployment. The explicitly
invoked RepairPermitAndObserve path holds the supervisor and collector locks,
verifies exact known installed config/runtime/backup receipt/manifest,
untouched original HOLD and absence of consumed/incomplete execution, locates
the real original temporary permit by its EXPECTED byte hash, and checks that
the defective claim is exactly canonical(original). Original defective bytes
and resume ticket are retained in a unique repair evidence directory.
It then restores exact original permit bytes at the existing digest name.

If scheduler had rejected the initial ticket during the bug, this manually
invoked repair requeues ONE initial ticket under the already installed
continuous permission, with a fresh30minute initial-start window and a repair
receipt/decision reference. This is not background renewal and does not grant
another segment after a consumed/uncertain recovery. A changed HOLD, active
execution/claim, missing original, unknown content, changed hashes, ambiguous
tickets or lock conflict blocks. Existing limits and source scope remain.

No runtime redeployment, task action/schedule/principal change, HOLD deletion,
collector start, archive download, trading, PIT or historical warehouse write.
The same command resumes the existing observer. Final original continuous
operation is still NOT_ATTESTED until actual receipt/rollover evidence.
