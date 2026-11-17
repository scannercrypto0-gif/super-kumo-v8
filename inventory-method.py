import collections, concurrent.futures, csv, datetime as dt, json, re, subprocess
from pathlib import Path

work=Path("work")
out=Path("outputs/atlas-consolidation-01")
out.mkdir(exist_ok=False)
repo=work/"continuity"
base="90af9794880cbeb00e7e974bfa906ff5e9666183"
open_prs=sum(json.loads((work/"consolidation-open-rest.json").read_bytes()),[])
checks=json.loads((work/"consolidation-checks.json").read_bytes())
hist=json.loads((work/"consolidation-closed.json").read_bytes())
merged={p["number"]:p for p in json.loads((work/"consolidation-merged.json").read_bytes())}
manifest=json.loads((work/"consolidation-candidates.json").read_bytes())
batches={item["source_pr"]:item for item in manifest["ordered_batches"]}
snap=dt.datetime.now(dt.timezone.utc)
pr_by_branch={p["head"]["ref"]:p["number"] for p in open_prs}

def git(*args):
    return subprocess.run(["git","-C",str(repo),*args],capture_output=True,encoding="utf-8",errors="replace")

def value(*args):
    r=git(*args)
    if r.returncode: raise RuntimeError((args,r.stderr))
    return r.stdout.strip()

def tree(sha):
    return {part.split("\t",1)[1]:part.split("\t",1)[0]
            for part in value("ls-tree","-r","-z",sha).split("\0") if part}

main_tree=tree(base)

def inspect(p):
    n=p["number"]
    head,target=p["head"]["sha"],p["base"]["sha"]
    if value("rev-parse",f"audit-pr/{n}")!=head:
        raise RuntimeError(f"#{n} changed since capture")
    common=value("merge-base",target,head)
    paths=value("diff","--name-only","--no-renames",common,head).splitlines()
    stage=tree(head)
    same=sorted(name for name in paths if stage.get(name)==main_tree.get(name))
    absent=sorted(name for name in paths if name in stage and name not in main_tree)
    changed=sorted(name for name in paths if name in stage and name in main_tree and name not in same)
    deletions=sorted(name for name in paths if name not in stage and name in main_tree)
    sim=git("merge-tree","--write-tree","--name-only",base,head)
    conflicts=[]
    if sim.returncode==1:
        conflicts=sim.stdout.split("\n\n",1)[0].splitlines()[1:]
    meta=checks[str(n)]
    exact=meta["observed_head"]==head
    check_list=meta["checks"] if isinstance(meta["checks"],list) else []
    reviews=meta["reviews"] if isinstance(meta["reviews"],list) else []
    parts=collections.Counter(path.split("/")[0] for path in paths)
    sensitivity=[]
    s=" ".join(paths).lower()
    for label, pattern in (
        ("SOURCE_CUSTODY",r"archive|custody|historical|raw_vault|source_view"),
        ("NETWORK_OR_OPERATIONS",r"collector|binance|websocket|scheduler|telegram|recovery|live_"),
        ("AUTHORITY_OR_EXECUTION",r"authority|promotion|paper|secretary|holdout|egress"),
        ("CI_OR_TOOLING",r"\.github/|requirements|pyproject|scripts/"),
        ("PERSISTENCE",r"migration|journal|storage|sqlite|backup"),
    ):
        if re.search(pattern,s): sensitivity.append(label)
    return dict(pr=n,title=p["title"],owner=p["user"]["login"],component_dirs=dict(parts),
        head=head,base=target,head_branch=p["head"]["ref"],base_branch=p["base"]["ref"],
        stack_parent=pr_by_branch.get(p["base"]["ref"]),branch_age_days=(snap-dt.datetime.fromisoformat(p["created_at"])).days,
        opened=p["created_at"],updated=p["updated_at"],draft=p["draft"],link=p["html_url"],own_merge_base=common,
        diff_paths=paths,changes_at_github={k:meta["detail"].get(k) for k in ("changed_files","additions","deletions")},
        main_tree_coverage={"identical_postimage":same,"absent_in_main":absent,"different_from_main":changed,"deletion_not_in_main":deletions},
        head_in_main=git("merge-base","--is-ancestor",head,base).returncode==0,
        mergeability={"github_target":meta["detail"].get("mergeable_state") if exact else "HEAD_MISMATCH",
            "git_main_simulation":{0:"CLEAN",1:"CONFLICT"}.get(sim.returncode,"UNAVAILABLE"),"main_conflicts":conflicts},
        exact_head_ci={"check_runs":check_list,"status":meta["status"],"status_contexts":meta["status_contexts"],
            "coverage_complete":isinstance(meta["checks"],list) and meta["checks_total"]==len(check_list)},
        github_reviews=reviews,review_read_available=isinstance(meta["reviews"],list),
        independent_review="See evidence index; per-PR independent acceptance is unverified unless cited",
        branch_protection="main has no reported classic protection or effective rules; topic branch rules not inferred",
        security_boundaries=sensitivity or ["GENERAL_REVIEW"])

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    rows=sorted(pool.map(inspect,open_prs),key=lambda row:row["pr"])
by={r["pr"]:r for r in rows}
path_index=collections.defaultdict(set)
for row in rows:
    for path in row["diff_paths"]: path_index[path].add(row["pr"])

scope_reasons={
 16:"Provisional foundation planning docs. Architecture and formal gate reconciliation stay in G0 review.",
 17:"Early architecture proposal. Review against #307 and current ADRs before documentation closure.",
 111:"Backup and scheduler have custody, key and operator-authority dependencies. Keep outside this release.",
 116:"Depends on #111 backup and historical custody authority. Isolate restore evidence before selecting.",
 208:"Explicit NO MERGE draft. Scientific hardening requires a frozen dependency and an independent scope audit.",
 211:"RAW vault custody scope requires separate rights/retention and original-source exact pins.",
 213:"Tooling outside runtime release. Review its authority and consumption before separate adoption.",
 214:"Dev environment toolkit is optional and not a runtime dependency. Verify isolated tooling scope separately.",
 217:"Coinbase is a separate source and the present research envelope is Binance-only.",
 224:"Collaboration process proposal. Disposition is deferred to PM governance review.",
 226:"Historical intake requires minimal parser/custody split and accepted rights. #304 candidate covers offline QA only.",
 258:"Explicit NO MERGE. Keep isolated bridge evidence and authority controls reviewable.",
 263:"Competing same-source draft with #264. Compare exact consumer schemas before any split.",
 264:"Synthetic same-source witness. Resolve #263 variant and pin accepted Core/Scanner contract before choosing.",
 267:"Stacked Factory E; compare default/research authority with Generic H #285 and split immutable store/report dependencies before admission.",
 271:"Wide integration conflicts. Windows operator delta requires #286 prospective observer, #305 pinned transport and Scanner/Factory packaging; current host evidence does not make the branch a release candidate.",
 275:"Owner-local NTFS/original custody stack. Requires rights, approved originals and offline import closure before any release.",
 277:"Retrospective NON_PIT Scanner stack. Require source-bound P0 closure and reconcile the #283 already-selected emitter.",
 284:"Authority separation reference. Main #285 closes the bounded synthetic seam. Review remaining branch diff before any claim of complete supersession.",
 286:"Mixed prospective worker and bounded original archive adapter. Separate the read path, pin Scanner and untangle archive custody imports before release.",
 289:"Forward evidence depends on #286 prospective observer. No standalone package while that import/clock seam remains unsettled.",
 291:"Factory cost-comparison stack needs immutable store/attempt contract and scientific authority remains gated.",
 292:"Bundled native-current fixture/source evidence needs provenance/retention classification and a minimal gateway split.",
 293:"Composite test/evidence branch depends on broad #271 input. Preserve pins; split a reusable acceptance seam after dependencies resolve.",
 296:"Retrospective batch evidence and authorized originals remain isolated. Requires dependency and original custody scope review.",
 297:"Capacity branch stacked on #291. Resolve Factory registry and compatibility before a deployment target exists.",
 300:"Multi-branch retrospective orchestration. Reports 15,381 modeled rows only; preserve assumed, retrospective and sealed-holdout flags.",
 301:"Prospective science depends on signed first-release/custody provenance and a sealed owner envelope.",
 305:"Full transport branch depends on #289 and includes mixed market/probe paths. Extract a research-only portable transport after pinning closure.",
 307:"Architecture v1 is provisional and includes dispatch tooling. Separate governance approval from implementation/automation.",
 309:"Ordered retrospective census lacks contemporaneous known-at and canonical Core parent. Keep out of prospective Paper.",
 312:"Daily freshness reader remains on #267; provider scheduling stays local. Split only after #267/#297 saved operator import closure.",
}
for r in rows:
    n=r["pr"]; paths=r["diff_paths"]; coverage=r["main_tree_coverage"]
    overlap=collections.Counter(i for path in paths for i in path_index[path] if i!=n)
    r["overlap_by_pr"]=dict(overlap.most_common())
    identical=len(paths)==len(coverage["identical_postimage"])
    if r["head_in_main"] or (paths and identical):
        verdict,why="ALREADY_IN_MAIN","Main contains the head by ancestry or exactly matches every changed path's postimage, including deletions."
    elif n in batches:
        item=batches[n]
        verdict,why="SPLIT_MINIMAL_DELTA",f"{item['batch']} prepares only {item['scope']}. Remaining paths are outside the candidate."
    elif n in (208,258):
        verdict,why="CLOSE_NO_MERGE",scope_reasons[n]
    elif n in (16,17,217,224,301,307) or 18<=n<=46:
        verdict,why="DEFER_G0_OR_SCIENCE",scope_reasons.get(n,"Stacked research prototype or statistical evidence. Retain the pinned artifact; require independent scientific contract and supported dependency closure before selecting for release.")
    elif n in scope_reasons:
        verdict,why="BLOCKED_WITH_REASON",scope_reasons[n]
    elif r["stack_parent"]:
        verdict,why="BLOCKED_WITH_REASON",f"Open base #{r['stack_parent']} is outside this merge manifest. Identify and validate a unique self-contained reduction against pinned main."
    elif r["mergeability"]["git_main_simulation"]=="CONFLICT":
        verdict,why="BLOCKED_WITH_REASON","Exact main merge simulation conflicts. Compare listed paths to current main and show required residual functionality before solving conflicts."
    else:
        verdict,why="BLOCKED_WITH_REASON","Exact residual paths are listed. A distinct required production contract and independently reviewed integration scope are unverified; leave out of this manifest."
    r["disposition"]=verdict
    r["reason"]=why
    r["candidate_batch"]=batches[n]["batch"] if n in batches else None

history=[]
for p in sorted(hist,key=lambda p:p["number"]):
    n=p["number"]; m=merged.get(n); commit=(m or {}).get("mergeCommit") or {}
    landing=commit.get("oid")
    in_main=bool(landing and git("merge-base","--is-ancestor",landing,base).returncode==0)
    history.append(dict(pr=n,title=p["title"],owner=(p.get("author") or {}).get("login"),head=p["headRefOid"],base=p["baseRefOid"],
                         branch=p["baseRefName"],merged=bool(m),merge_commit=landing,merge_commit_in_main=in_main,
                         scope_files=p["changedFiles"],link=p["url"],closed_at=p["closedAt"],
                         disposition="ALREADY_IN_MAIN" if in_main else "BLOCKED_WITH_REASON" if m else "CLOSE_NO_MERGE",
                         reason="Landing commit is in pinned main." if in_main else
                                "Merged landing is outside pinned main; inspect coverage separately." if m else
                                "Closed without an observed merge; closed state supplies no main-coverage claim."))
meta=dict(captured_at=snap.isoformat(),open_prs=len(rows),drafts=sum(r["draft"] for r in rows),
          baseline=base,main_classic_protection="BRANCH_NOT_PROTECTED (HTTP 404)",
          main_effective_rules=[],classification_counts=dict(collections.Counter(r["disposition"] for r in rows)),
          open=rows,historical_closed=history)
(out/"pr-inventory.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
with (out/"pr-disposition.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f)
    w.writerow(("PR","Title","Owner","Head","Base","Base branch","Age days","Main identical","Own paths","Main conflicts",
                "Exact CI success","Exact CI other","GitHub reviews","Disposition","Reason","Batch","Link"))
    for r in rows:
        checks=r["exact_head_ci"]["check_runs"]
        w.writerow((r["pr"],r["title"],r["owner"],r["head"],r["base"],r["base_branch"],r["branch_age_days"],
                    len(r["main_tree_coverage"]["identical_postimage"]),len(r["diff_paths"]),r["mergeability"]["git_main_simulation"],
                    sum(c["conclusion"]=="success" for c in checks),sum(c["conclusion"]!="success" for c in checks),
                    len(r["github_reviews"]),r["disposition"],r["reason"],r["candidate_batch"],r["link"]))
print({k:v for k,v in meta.items() if k not in ("open","historical_closed")})
print("hist",len(history),"merged",len(merged),"landed",sum(r["merge_commit_in_main"] for r in history))
print("conflicts",sum(r["mergeability"]["git_main_simulation"]=="CONFLICT" for r in rows))
