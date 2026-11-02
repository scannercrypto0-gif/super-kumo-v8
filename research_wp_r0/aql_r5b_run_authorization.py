"""R5B workflow approval policy only; no network, source/PIT or trading authority."""
import datetime
import re
import fnmatch

PHRASE='GO_RUN_R5B_PUBLIC_WS_UNVERIFIED_960S_1BAR'


def approval_body(owner,approved_sha):
    return ('OWNER APPROVED ONE-TIME RUN '+approved_sha+': '+PHRASE+
            '; operator='+owner+'; retention=7days; witness=UNVERIFIED; no-trading; no-REST; no-reconnect.')


def verify_comment(comment,*,repo,actor,approved_sha,comment_id,now):
    owner=repo.split('/')[0]
    if not re.fullmatch(r'[a-f0-9]{40}',approved_sha) or not re.fullmatch(r'[0-9]{1,20}',comment_id):
        raise ValueError('EXACT_SHA_AND_COMMENT_REQUIRED')
    if actor!=owner or comment['user']['login']!=owner:
        raise ValueError('OWNER_ONLY_RUN_APPROVAL')
    if comment['issue_url']!='https://api.github.com/repos/'+repo+'/issues/180':
        raise ValueError('APPROVAL_ISSUE_MISMATCH')
    # Mentioning a proposed run/token in a delivery or a denial is NOT consent.
    if comment['body'].strip()!=approval_body(owner,approved_sha):
        raise ValueError('EXACT_RUN_SCOPE_NOT_APPROVED')
    created=datetime.datetime.fromisoformat(comment['created_at'].replace('Z','+00:00'))
    if not 0<=(now-created).total_seconds()<=86400:
        raise ValueError('OWNER_APPROVAL_MUST_BE_FRESH_WITHIN24H')
    return 'R5B-one-shot-'+approved_sha+'-'+comment_id


def deny_previous_runs(runs,*,title,current_run_id):
    if any(int(r['id'])<int(current_run_id) and r['display_title']==title for r in runs):
        raise ValueError('ONE_TIME_APPROVAL_ALREADY_CONSUMED')


def legacy_delta_needed(changed,patterns):
    """Keep accepted legacy suites scoped to THEIR code/tests, not PR base diff."""
    return any(fnmatch.fnmatchcase(path,pattern) for path in changed for pattern in patterns)
