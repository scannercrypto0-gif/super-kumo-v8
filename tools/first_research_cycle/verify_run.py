"""Read-only independent Factory result-population and paired-shadow readback."""
import argparse
from collections import Counter
from decimal import Decimal,localcontext
import json
from pathlib import Path
import sqlite3
from tools.first_research_cycle.market_cycle import sha,need,persist


def verify(root):
    report=json.loads((root/'result.json').read_text())
    need(sha({k:v for k,v in report.items() if k!='sha256'})==report['sha256'],'RESULT_SEAL')
    plan=json.loads((root/'market-plan.json').read_text());need(sha(plan)==report['plan_sha256'],'PLAN_PARENT')
    con=sqlite3.connect((root/'factory.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        need(con.execute('select count(*) from experiments').fetchone()[0]==1,'TRIAL_POPULATION')
        records=con.execute('select canonical_sha256,document from factory_h_research_results_v1').fetchall()
        need(len(records)==1,'RESULT_POPULATION')
        document=json.loads(records[0][1])
        need(sha({k:v for k,v in document.items() if k!='sha256'})==records[0][0]==report['result_store_sha256'],'NATIVE_STORE_SEAL')
    finally:con.close()
    need(document['actual_fills'] is None and document['trading_authority']=='NONE','FALSE_AUTHORITY')
    rows=document['outcomes'];keys=[(r['cohort'],r['entry_id'],r['scenario'],r['policy']) for r in rows]
    need(len(rows)==len(set(keys))==report['populations']['cost_rows'],'DUPLICATE_OR_MISSING_COST_ROW')
    need(dict(Counter(r['status'] for r in rows))==report['outcome_status_counts'],'STATUS_POPULATION')
    indexed=dict(zip(keys,rows));paired={}
    with localcontext() as c:
        c.prec=40
        for key,summary in report['comparisons'].items():
            parts=key.split(':');part=None
            if len(parts)==4:part,cohort,scenario,policy=parts
            else:cohort,scenario,policy=parts
            subset=[r for r in rows if (r['cohort'],r['scenario'],r['policy'])==(cohort,scenario,policy)
                    and (part is None or r['partition']==part)]
            need(len(subset)==summary['attempted_entry_count'],'SUMMARY_DENOMINATOR')
            known=[r for r in subset if r['status']=='MODEL_ONLY']
            need(len(known)==summary['known_subset_only_count'],'KNOWN_POPULATION')
            for field,diagnostic in (('gross_return','known_subset_gross_diagnostic_sum'),('net_return','known_subset_net_diagnostic_sum')):
                need(sum((Decimal(r[field]) for r in known),Decimal(0))==Decimal(summary[diagnostic]),'INDEPENDENT_TOTAL_MISMATCH')
            if part is not None or policy!='A':continue
            for shadow in ('B','C'):
                pairs=[(r,indexed[(cohort,r['entry_id'],scenario,shadow)]) for r in subset]
                both=[(a,b) for a,b in pairs if a['status']==b['status']=='MODEL_ONLY']
                deltas=[Decimal(b['net_return'])-Decimal(a['net_return']) for a,b in both]
                paired[cohort+':'+scenario+':A_vs_'+shadow]=dict(total_paired_entries=len(pairs),
                    known_both_count=len(both),unknown_pair_count=len(pairs)-len(both),
                    full_population_mean_net_delta=(str(sum(deltas,Decimal(0))/len(pairs)) if len(both)==len(pairs) and pairs else None),
                    known_subset_only_net_delta_sum=str(sum(deltas,Decimal(0))),
                    verdict='DESCRIPTIVE_ASSUMED_EXECUTION_NO_WINNER_NO_ALPHA',paired_identity='SAME_SOURCE_FROZEN_ENTRY_AND_INITIAL_RISK')
        for row in rows:
            for leg in row['legs']:
                need(leg['accounting_asof_ms']<=plan['validation_end_ms'],'HOLDOUT_LOOKAHEAD')
            if row['status']=='MODEL_ONLY':
                need(sum((Decimal(x['fraction_of_initial_notional']) for x in row['legs']),Decimal(0))==1,'FRACTION_CONSERVATION')
                need(Decimal(row['gross_return'])-Decimal(row['net_return'])==Decimal(row['total_cost_bps'])/10000,'DOUBLE_COST')
    body=dict(schema='aql.first-cycle.independent-verification.v1',result_sha256=report['sha256'],
        status='PASS_INDEPENDENT_ACCOUNTING_AND_POPULATION_READBACK',native_experiments=1,native_result_packages=1,
        verified_cost_rows=len(rows),paired_exit_shadow=paired,
        scientific_status='REAL_PIT_OOS_BLOCKED',trading_authority='NONE',actual_fills=None,
        attribution='Binance Vision; derived analysis CC BY-NC-SA4.0')
    return {**body,'sha256':sha(body)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();persist(args.output,verify(args.run));print('READ_ONLY_VERIFICATION_PASS')
