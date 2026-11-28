# Scientific qualification readiness · #299

Owner order [#299/7236192166](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/299#issuecomment-7236192166).
This packet extends [Factory/Lab #254](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/254#issuecomment-6733302653)
and the [Factory evidence store #267](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/267).
The integration continuation [#205](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-7236133591)
owns shared integration and host evidence. This delta is confined to #301's readiness kit and its CI.

## Gates and evidence

| Stage | Evidence to review | Current boundary |
| --- | --- | --- |
| S0 | `BASELINE.md`, pins below, prior #299 reports | Retained 5,856-slot and 15,282-outcome cycle is retrospective. The existing G4 and Shadow acceptances retain their original scope. |
| S1 | Canonical protocol, plan, freeze and trial census | Executable fixture with three attempts, fixed BASE, three cost and three exit models, 54 reserved comparison cells, no optional stopping. The proposed real metric policy requires a future freeze. |
| S2 | Native admission and ordered Scanner ACK tests, causal prefix tests | Requires publication and durable ACK before signal use. Source swaps, revisions and missing or reordered receipts fail closed. The two embargoes separate the fixture partitions. |
| S3 | Factory report and cost-once checks | Taker, passive entry with market exit, and stress. Nonfill and partial fill are explicit. Queue/priority, market impact and liquidity measurement require venue evidence. |
| S4 | `qualification.json`, native Factory outcomes and Lab denominator | 50 BASE/SHADOW pairs, 300 arm/horizon slots. The native Lab preserves missingness and cannot infer arm effect from common descriptive windows. There are 72 execution outcomes and no qualified statistical sample. |
| S5 | Holdout lock, negative promotion and proof tests | No holdout prices stored or read. Signed-role and logical isolation tests are fixture-only. Actual independent operator/researcher/custodian OS ACL and one-shot release remain unverified. |
| S6 | Exact-head matrix jobs and manifest | Two isolated process outputs and crash/restart must produce the same canonical decision; Windows and Ubuntu evidence is linked from #301 after publication. |
| S7 | Independent Audit #134 | Acceptance requires Audit of this material delta and closure of counterexamples. |

### Pinned inputs

| Reference | SHA at intake | Use |
| --- | --- | --- |
| #290 | `612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d` | Read-only Core admission and archive custody |
| #291 | `ea4ffd5ce278d93588338122ab6ac1af8ec4da26` | Pinned Factory evaluator, model and journal |
| #296 | `eb49308d61ffdfc24ed5032df2cb541f37c48bfe` | Prior retrospective report only |
| #297 | `dd3e149afe73d9d04c9892ad35005b04fb675fff` | Prior Factory consumer evidence only |
| #267 | `1df72b3cdc3dd551fd6d42ec2b83d4925c4b7cdd` | Shadow evidence and saved-Lab readback |
| #301 | `cd0ae17a6e79adee0b1d388a4c585bbd2aeacb4b` | Intake source for this delta |
| #271, #336, #333 | `ed6f043`, `f781595`, `011bc18` | Integration and Core-owned references; no source mutation |

Previous exact-head cross-platform evidence covered #301 at `8adea8c`. Later local acceptance at `dda94f7` and `cd0ae17` is scoped to those changes. The exploratory witness waiver does not supply real prospective evidence. The new matrix includes both readiness and promotion tests.

## Reproduction

From a disposable checkout at the review head, set `PYTHONPATH` to `src:.` on Ubuntu or `src;.` on Windows. Use Python 3.13 and pytest 9.0.2 for the CI-equivalent command. The dependency command stages exact Git objects from the project repository only.

```text
python -B -m tools.pit_oos_readiness.dependencies --fetch
python -B -m pytest tools/pit_oos_readiness -q
python -B -m tools.pit_oos_readiness.readiness pit-evidence
python -B -m tools.pit_oos_readiness.manifest pit-evidence
```

Use a fresh output directory. The decision binds the protocol, freeze, ordered census, Factory report and qualification report. The manifest records the source tree and raw output hashes.

## Metric policy to approve before a real cohort

- Freeze the primary paired estimand, minimum worthwhile net uplift, maximum tolerable drawdown, minimum sample/coverage, accepted stress limits and regime definitions. Use identical slots, source versions, execution assumptions and risk constraints for both arms. Publish complete-case counts and missingness by arm and regime. An unresolved outcome cannot be priced as zero. A modeled nonfill is zero return and stays in its attempted-entry denominator.
- Fixture net return is the arithmetic sum of Factory trade results after costs divided by all attempted entries in a complete cell. Fixture drawdown is the native compounded trade-close peak-to-trough measure. A future portfolio drawdown and Sharpe require a separately defined, marked equity path. Report unannualized mean excess slot return divided by sample deviation on a frozen regular grid, with the risk-free convention stated. Zero variance or insufficient data yields no Sharpe.
- Propose two-sided family-wise alpha 0.05 and 80% power for owner review. For planning, freeze the smallest material paired effect and estimate long-run variance on development data only. A first-pass slot requirement is `(z(1-alpha_cell/2)+z(power))^2 * long_run_variance / effect^2`; round up, reserve for expected missingness, and verify prospective power under moving-block simulations on development data. Lack of defensible pilot variance, independent blocks, or adequate predeclared regime coverage leaves sample size unresolved.
- Freeze a moving-block interval method, grid, block length, seed and resample count from development only. Select a block length that covers overlap and estimated serial dependence. Use the same time indices for both arms. Allocate alpha over the full frozen family and retain failed and unscanned trials. An adjusted interval entirely above the minimum material effect supports PASS and entirely below supports FAIL on that efficacy criterion. An overlapping interval or inadequate sample is INCONCLUSIVE. Independent admissibility, risk and cost gates are additionally required.
- Pin regime definitions using only decision-time information. Report matched counts and outcome coverage for each predeclared regime and cost case without reselecting exits. Reconcile incomplete data, negative controls, cost components and repeated attempts before review.

The statistical planning formulas specify a proposal. The existing fixture exercises the interval decision classifier and deliberately withholds empirical Sharpe, confidence intervals and power because its samples are synthetic and insufficient. There is no empirical venue-liquidity claim.

## External proof and sign-off

Use the single pending `owner-envelope.json` for source rights, future windows and budget, independent timing witness, immutable custody, blind holdout role separation and the approved hypothesis/metric freeze. Exact independent ACL/holdout verification requires separately controlled test roles and readback evidence. `SCIENTIFIC_QUALIFICATION_READINESS_ACCEPTED` is reserved for complete engineering evidence and independent Audit. `REAL_PIT_OOS_BLOCKED`, `PAPER_BLOCKED` and trading authority `NONE` apply throughout this packet.
