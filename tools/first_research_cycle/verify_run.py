"""Read-only independent Factory result-population and paired-shadow readback."""
import argparse
from collections import Counter
from decimal import Decimal,localcontext
import json
from pathlib import Path
import re
import sqlite3
from tools.first_research_cycle.market_cycle import canonical,sha,need,persist,scanner_receipt


def verify_scanner(root, report, plan, experiment, document, entry_id):
    path = root/'scanner-census.json'
    need(path.is_file() and not path.is_symlink(), 'SCANNER_RECEIPT_MISSING')
    with path.open('rb') as stream:
        raw = stream.read(5_000_001)
    need(len(raw) <= 5_000_000, 'SCANNER_RECEIPT_SIZE')
    receipt = json.loads(raw)
    need(raw == canonical(receipt) + b'\n' and
         sha(receipt) == report['scanner_receipt_sha256'], 'SCANNER_RECEIPT_SEAL')

    candidate = json.loads((root/'candidate.json').read_bytes())
    native_plan = json.loads((root/'native-plan.json').read_bytes())
    need(sha(native_plan) == report['native_plan_sha256'] == candidate['search_plan_digest'] ==
         document['native_plan_sha256'] and native_plan['protocol_digest'] == report['plan_sha256'],
         'SCANNER_NATIVE_PLAN')
    need(sha({k:v for k,v in candidate.items() if k != 'package_digest'}) ==
         candidate['package_digest'] == report['candidate_package_sha256'] ==
         experiment['parent_receipt_sha256'] == document['candidate_package_sha256'], 'SCANNER_CANDIDATE')
    attempt, = experiment['attempts']
    need(attempt['candidate_id'] == candidate['candidate_id'] and
         attempt['source_receipt_sha256'] == candidate['package_digest'], 'SCANNER_ATTEMPT')
    ledger = json.loads((root/'discoverer-ledger.json').read_bytes())
    need([row['state'] for row in ledger] == ['REGISTERED', 'PENDING', 'COMPLETE'],
         'CORRUPT_OR_MISSING_LEDGER')
    previous = '0' * 64
    for index, row in enumerate(ledger):
        need(row['entry_index'] == index and row['predecessor_digest'] == previous and
             sha({k:v for k,v in row.items() if k not in ('entry_digest', 'wall_clock_ns')}) == row['entry_digest'] and
             row['attempt_id'] == attempt['attempt_id'] and row['candidate_id'] == candidate['candidate_id'] and
             row['search_plan_digest'] == report['native_plan_sha256'] and
             row['strategy_digest'] == plan['strategy']['digest'], 'SCANNER_ATTEMPT_CHAIN')
        previous = row['entry_digest']
    need(ledger[1]['entry_digest'] == candidate['attempt_ledger_head'], 'SCANNER_ATTEMPT_PARENT')

    rows = receipt['decisions']
    need(isinstance(rows, list) and 0 < len(rows) <= 8192 and
         len(rows) == plan['expected_bars'] == report['populations']['scanner_slots'], 'SCANNER_POPULATION')
    need(sha(rows) == report['decision_census_sha256'] == document['decision_census_sha256'],
         'SCANNER_CENSUS_MEMBERSHIP')
    need(receipt == scanner_receipt(report, plan, experiment, candidate, rows), 'SCANNER_RECEIPT_LINK')
    need(sha(report['source']) == document['source_sha256'] == experiment['source_sha256'] ==
         candidate['source_manifest_sha256'] == native_plan['dataset_digest'] and
         report['source_class'] == document['source_class'] == plan['source_class'],
         'SCANNER_SOURCE_PARENT')
    need(sha(plan['strategy']) == experiment['config_sha256'] and
         plan['strategy']['digest'] == experiment['strategy_definition_sha256'] ==
         candidate['strategy_definition_digest'], 'SCANNER_STRATEGY')
    need(dict(Counter(row['state'] for row in rows)) == report['populations']['scanner_census'],
         'SCANNER_CENSUS_COUNTS')
    for position, row in enumerate(rows):
        expected_open = plan['first_open_ms'] + position * 900_000
        need(row['open_ms'] == expected_open and row['decision_cutoff_ms'] == expected_open + 900_000,
             'SCANNER_CUTOFF')
        need(row['known_at_ms'] is None and row['availability'] == 'RETROSPECTIVE_NON_PIT' and
             row['strategy_sha256'] == receipt['strategy_sha256'] and
             re.fullmatch('[0-9a-f]{64}', row['source_row_sha256']) is not None, 'SCANNER_ROW')
    linked = None
    if entry_id is not None:
        need(re.fullmatch(r'entry(?:0|[1-9][0-9]{0,3})', entry_id) is not None, 'SCANNER_ENTRY_ID')
        position = int(entry_id[5:])
        need(position < len(rows) - 1 and rows[position]['state'] == 'ENTRY_SIGNAL' and
             rows[position]['decision_cutoff_ms'] < plan['validation_end_ms'], 'SCANNER_ENTRY_STATE')
        matches = [row for row in document['outcomes']
                   if row['cohort'] == 'CANDIDATE' and row['entry_id'] == entry_id]
        partition = 'TRAIN' if rows[position]['open_ms'] < plan['train_end_ms'] else 'VALIDATION'
        need(matches and all(row['attempt_id'] == attempt['attempt_id'] and
                             row['partition'] == partition for row in matches), 'SCANNER_FACTORY_ENTRY')
        linked = dict(entry_id=entry_id, position=position, decision_sha256=sha(rows[position]),
                      decision=rows[position], attempt_id=attempt['attempt_id'],
                      candidate_id=candidate['candidate_id'], experiment_id=experiment['experiment_id'])
    return dict(status='LINK_PROVED_RETROSPECTIVE_NON_PIT', core='SOURCE_BLOCKED',
                known_at='KNOWN_AT_UNATTESTED', receipt_sha256=sha(receipt), opportunity=linked)


def verify(root, *, entry_id=None):
    report=json.loads((root/'result.json').read_text())
    need(sha({k:v for k,v in report.items() if k!='sha256'})==report['sha256'],'RESULT_SEAL')
    plan=json.loads((root/'market-plan.json').read_text());need(sha(plan)==report['plan_sha256'],'PLAN_PARENT')
    con=sqlite3.connect((root/'factory.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        need(con.execute('select count(*) from experiments').fetchone()[0]==1,'TRIAL_POPULATION')
        experiment_record = con.execute('select experiment_id, sha, document from experiments').fetchone()
        records=con.execute('select canonical_sha256,document from factory_h_research_results_v1').fetchall()
        need(len(records)==1,'RESULT_POPULATION')
        document=json.loads(records[0][1])
        need(sha({k:v for k,v in document.items() if k!='sha256'})==records[0][0]==report['result_store_sha256'],'NATIVE_STORE_SEAL')
    finally:con.close()
    scanner = None
    if 'scanner_receipt_sha256' in report:
        experiment = json.loads(experiment_record[2])
        need(sha({k:v for k,v in experiment.items() if k != 'sha256'}) ==
             experiment['sha256'] == experiment_record[1] == report['factory_experiment_sha256'] ==
             document['factory_experiment_sha256'] and
             experiment_record[0] == experiment['experiment_id'] == document['experiment_id'],
             'SCANNER_FACTORY_EXPERIMENT')
        scanner = verify_scanner(root, report, plan, experiment, document, entry_id)
    else:
        need(entry_id is None, 'BLOCKED_SCANNER_INDIVIDUAL_RECEIPT')
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
    if scanner is not None:
        body['scanner_membership'] = scanner
    return {**body,'sha256':sha(body)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--entry-id')
    args=p.parse_args();persist(args.output,verify(args.run,entry_id=args.entry_id));print('READ_ONLY_VERIFICATION_PASS')
