import json, os, subprocess
from pathlib import Path

root = Path("work/continuity").resolve()
scratch = root.parent
base = "90af9794880cbeb00e7e974bfa906ff5e9666183"
env = dict(os.environ, GIT_INDEX_FILE=str(scratch/"consolidation-candidates.index"),
           GIT_COMMITTER_NAME="Codex", GIT_COMMITTER_EMAIL="codex@openai.com",
           GIT_COMMITTER_DATE="2026-11-17T08:45:00Z")

def git(*args, data=None, raw=False):
    result = subprocess.check_output(["git","-C",str(root),*args],input=data,env=env)
    return result if raw else result.decode("utf-8").strip()

batches = [
 ("B01","G1 isolated foundation",287,["src/aql/foundation","tests/test_g1_foundation_closeout.py","tools/measure_g1_foundation_closeout.py","docs/evidence/g1_foundation_closeout_ledger.json","docs/evidence/g1_foundation_closeout_resources.json"],"Foundation census, as-of checks, bounded scheduling"),
 ("B02","Historical source QA",304,["tools/historical_source_qa"],"Offline fixture/archive validation; no acquisition or scheduling"),
 ("B03","Core custody projections",308,["src/aql/archive/discoverer_view.py","src/aql/archive/scanner_view.py","src/aql/archive/source_poll.py","src/aql/archive/source_registry.py","src/aql/archive/source_view.py","src/aql/recovery/gap_recovery.py","tests/test_core_discoverer_followup.py","tests/test_core_source_view.py","docs/core/core-c1-c6-source-repository.md","docs/core/core-discoverer-followup.md","docs/core/source-coverage-v1.json"],"Read-only projections and fixture-scoped recovery fence"),
 ("B04","Isolated G3 simulator",288,["src/aql/paper_sim","tests/paper_sim","docs/g3-paper-sim.md"],"TEST_ONLY simulator and native position journal; excludes promotion/dashboard"),
]
manifest=[]
parent=base
for key, title, number, paths, scope in batches:
    source=git("rev-parse",f"audit-pr/{number}")
    if git("merge-base",base,source)!=base:
        raise RuntimeError((number,"source not based on pinned main"))
    patch=git("diff","--binary","--full-index",base,source,"--",*paths,raw=True)
    if not patch:
        raise RuntimeError((number,"empty patch"))
    git("read-tree",parent)
    git("apply","--cached","--check",data=patch)
    git("apply","--cached",data=patch)
    tree=git("write-tree")
    changed=git("diff","--name-only",parent,tree).splitlines()
    for name in changed:
        if git("ls-tree",tree,"--",name)!=git("ls-tree",source,"--",name):
            raise RuntimeError((number,name,"source blob differs"))
    git("diff","--check",parent,tree)
    name,email,date=git("show","-s","--format=%an%x00%ae%x00%aI",source).split("\0")
    env.update(GIT_AUTHOR_NAME=name,GIT_AUTHOR_EMAIL=email,GIT_AUTHOR_DATE=date)
    prior=manifest[-1]["batch"] if manifest else None
    message=f"{key}: {title}\n\nPrepared only for independent review.\n\nSource-PR: {number}\nSource-Head: {source}\n"
    head=git("commit-tree",tree,"-p",parent,data=message.encode())
    git("update-ref",f"refs/heads/consolidation-review/{key.lower()}",head)
    manifest.append(dict(batch=key,depends_on=prior,base=parent,candidate=head,tree=tree,source_pr=number,
                         source_head=source,source_commits=git("log","--format=%H",f"{base}..{source}","--",*paths).splitlines(),
                         paths=changed,scope=scope,rollback="Revert this batch in reverse dependency order after approval"))
    parent=head
(scratch/"consolidation-candidates.json").write_text(json.dumps({"main":base,"ordered_batches":manifest},indent=2),encoding="utf-8")
print([(row["batch"],row["candidate"],len(row["paths"])) for row in manifest])
