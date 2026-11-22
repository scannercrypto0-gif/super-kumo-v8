# Atomic supervisor preflight and deployment

Owner c1547fa9 run passed initial baseline assessment, then rejected Apply with OWNER_HOST_PREFLIGHT_BLOCKED. No deployment or task start was reported. The original failing predicate was not retained by the helper, so the owner's precise host cause remains unproven.

Code review identified a concrete time-of-check/time-of-use window: Apply authorized an unlocked snapshot, acquired supervisor.lock, then authorized another snapshot. The scheduled task can transiently become Running between the initial assessment and either authorization. The unlocked authorization served no durable mutual exclusion.

Apply now acquires the existing supervisor lock first and authorizes a fresh snapshot under that same lock, retained through clock qualification, staging, task-pin readback and COMMIT. There is no authorization bypass: all exact identity, expiry, runtime, configuration, collector, quota and scope checks still run. Lock contention receives at most three minutes of waiting, without task starts/stops or changes. A locked authorization rejection retries only a sole TASK_NOT_QUIESCENT_READY with enabled task, zero collectors and proven lock. Every other rejection remains terminal. Failed attempts release their lock before waiting.

Python retains an allow-listed preflight rejection (all blocker codes, task state/enabled, collector count, lock availability). The native UTF8 helper carries this context to the public receipt; gate-stage rejection also keeps its original reason. The unified bootstrap saves an Apply refusal as a create-once owner-results JSON, with its REPORT_FILE path. No task XML, command lines, host file paths or raw market payloads are included.

Regression execution uses the actual PowerShell helper extracted from its AST, real exclusive filesystem locks and mocked task/authorization responses. It proves authorization happens while competing lock acquisition fails, the narrow transient is retried, the lock remains held after success, terminal failures are not retried and failed attempts release the lock. Python covers classification and privacy. Native child-process wire tests preserve blocker details on Windows PowerShell 5/7 and Ubuntu PowerShell 7.

Historical warehouse and daily task untouched. No quota/circuit reset, automatic HOLD clearance, source fetch, merge, trading, or owner-host continuous-operation attestation is implied by offline acceptance.
