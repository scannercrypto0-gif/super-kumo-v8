"""Read-only joins of the already accepted, persisted G4 current-head bundle.

No registry/evaluator is invoked or reconstructed. Inner H packages/ledgers are
retained as native parent digests; verification does not pretend to reopen their
unpersisted bodies or independently attest the old producer's calculations.
"""
from collections import Counter

COMMIT = '7b6c8d82ca8111f5fa15dee5e6823bc39289b48c'
FILES = ('closeout.json','registry.json','frozen-v2/checkpoint.json',
         'frozen-v2/originals.json','frozen-v2/proposal.json','frozen-v2/registration.json')
DEPS = {'factory':'04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf',
        'discoverer':'c568e3b281795f9eef2165c0e6f571b87157a23c',
        'scanner':'ccf57ad3db7e71290a8321840e800136567e3af4'}
STATES = ('REGISTERED','PENDING','COMPLETE','INVALID','FAILED','ABANDONED')
TRANSITIONS = {'REGISTERED':{'PENDING','INVALID','ABANDONED'},
               'PENDING':{'COMPLETE','FAILED','ABANDONED'}}


def consume(root, spec, *, read, sha, need, sealed, boundary):
    need(type(spec) is dict and set(spec) == {'schema','source_commit','files'}
         and spec['schema'] == 'aql.gateway.persisted-g4-bundle.v1'
         and spec['source_commit'] == COMMIT and set(spec['files']) == set(FILES),
         'RESEARCH_BUNDLE_VERSION_OR_FILES')
    docs = {}
    for name in FILES:
        doc = read(root / 'g4_current_head' / name)
        need(sha(doc) == spec['files'][name], 'RESEARCH_FILE_DIGEST')
        boundary(doc)
        docs[name] = doc
    closeout, registry = docs['closeout.json'], docs['registry.json']
    proposal, registration = docs['frozen-v2/proposal.json'], docs['frozen-v2/registration.json']
    checkpoint, originals = docs['frozen-v2/checkpoint.json'], docs['frozen-v2/originals.json']
    for doc, key in ((closeout,'sha256'),(proposal,'proposal_sha256'),(registration,'sha256')):
        sealed(doc, key)
    generation, variants, trial = (closeout[k] for k in ('generation','variant_registry','trial'))
    for doc, key in ((generation,'receipt_sha256'),(variants,'sha256'),(trial,'sha256')):
        sealed(doc, key)
    need(proposal['schema_version'] == 'aql.g4.discoverer.preregistered-candidate-proposal.v1'
         and generation['schema_version'] == 'aql.g4.discoverer.factory-existing-registry-join.v1'
         and variants['schema'] == 'aql.factory.e.research-experiment.v1'
         and registration['schema'] == 'aql.g4.synthetic.wp03.registration.v1', 'RESEARCH_NATIVE_VERSION')
    need(all(registration['dependency_heads'][k] == v for k,v in DEPS.items()), 'RESEARCH_DEPENDENCY_SWAP')
    need(closeout['proposal_sha256'] == proposal['proposal_sha256'] ==
         registration['current_head_proposal'] == generation['candidate_proposal_sha256']
         and closeout['registration_sha256'] == registration['sha256'] == trial['trial_id'],
         'RESEARCH_PROPOSAL_REGISTRATION_PARENT')
    need(proposal['candidate_id'] == registration['candidate']['candidate_id']
         and proposal['candidate_package_sha256'] == registration['candidate']['package_digest'] ==
             originals['candidate_package']['package_digest'] == generation['candidate_package_sha256']
         and proposal['strategy_definition_sha256'] == variants['strategy_definition_sha256'] ==
             registration['candidate']['strategy_definition_digest']
         and proposal['source_manifest_sha256'] == variants['source_sha256'] ==
             registration['fixture_source_manifest_sha256'] == registration['nomination']['source_manifest_sha256'],
         'RESEARCH_CANDIDATE_SOURCE_SWAP')
    need(proposal['scanner_binding_sha256'] == registration['binding']['binding_sha256'] == generation['scanner_binding_sha256']
         and proposal['scanner_plugin_sha256'] == registration['binding']['scanner_plugin_sha256'] ==
             generation['scanner_plugin_sha256'] == registration['plugin']['sha256'], 'RESEARCH_SCANNER_PARENT')
    for name, field in (('hypothesis','hypothesis_digest'),('search_plan','plan_digest'),
                        ('validation_protocol','protocol_digest'),('scanner_binding','binding_sha256'),
                        ('synthetic_nomination','nomination_digest')):
        sealed(originals[name],field)
    need(originals['scanner_plugin']['sha256'] == sha(originals['scanner_plugin']['payload'])
         and originals['scanner_plugin'] == registration['plugin']
         and originals['scanner_binding'] == registration['binding']
         and originals['search_plan']['plan_digest'] == proposal['search_plan_sha256'] == generation['search_plan_sha256']
         and originals['hypothesis']['hypothesis_digest'] == proposal['hypothesis_sha256']
         and originals['validation_protocol']['protocol_digest'] == proposal['protocol_sha256']
         and originals['baseline_id'] == proposal['paired_baseline_id'] == generation['paired_baseline_id']
         and originals['frozen_trial_budget'] == proposal['frozen_trial_budget'], 'RESEARCH_FROZEN_ORIGINALS_PARENT')
    need(variants['parent_receipt_sha256'] == generation['receipt_sha256']
         and variants['result_sha256'] == trial['sha256']
         and variants['experiment_id'] == 'G4-VARIANTS-' + registration['sha256']
         and generation['factory_experiment_id'] == 'G4-GENERATION-' + registration['sha256'],
         'RESEARCH_FACTORY_RESULT_PARENT')

    def ledger(entries):
        need(type(entries) is list and 0 < len(entries) <= 4096, 'RESEARCH_LEDGER_BOUND')
        previous, last = '0'*64, {}
        for index, entry in enumerate(entries):
            need(type(entry['entry_index']) is int and entry['entry_index'] == index
                 and entry['predecessor_digest'] == previous
                 and entry['entry_digest'] == sha({k:v for k,v in entry.items()
                                                  if k not in ('entry_digest','wall_clock_ns')})
                 and entry['state'] in STATES, 'RESEARCH_LEDGER_CHAIN')
            old = last.get(entry['attempt_id'])
            need(entry['state'] == 'REGISTERED' if old is None else
                 entry['state'] in TRANSITIONS.get(old['state'],set()), 'RESEARCH_LEDGER_TRANSITION')
            if old:
                need(all(entry[k] == old[k] for k in ('candidate_id','family_id','strategy_digest',
                     'search_plan_digest','nomination_digest')), 'RESEARCH_LEDGER_IDENTITY')
            last[entry['attempt_id']] = entry
            previous = entry['entry_digest']
        return last, previous

    latest, head = ledger(checkpoint['entries'])
    need(checkpoint['sequence'] == 1 and checkpoint['ledger_head'] == head
         and checkpoint['entries_digest'] == sha(checkpoint['entries'])
         and checkpoint['checkpoint_sha'] == sha(dict(
             schema_version='aql.discoverer.e.durable-checkpoint.v1',sequence=1,
             predecessor_sha='0'*64,record={k:checkpoint[k] for k in ('entries','entries_digest','ledger_head')})),
         'RESEARCH_CHECKPOINT_SEAL')
    need(proposal['ledger_checkpoint_sha256'] == checkpoint['checkpoint_sha'] == generation['discoverer_checkpoint_sha256']
         and proposal['attempt_ledger_head_sha256'] == head == generation['discoverer_ledger_head_sha256'],
         'RESEARCH_CHECKPOINT_PARENT')
    count = Counter(e['state'] for e in latest.values())
    census = dict({k:count[k] for k in STATES}, incomplete_attempts=count['REGISTERED']+count['PENDING'],
                  total_ledger_events=len(checkpoint['entries']), total_unique_attempts=len(latest))
    need(census == proposal['attempt_census'] == generation['discoverer_attempt_census']
         and generation['factory_attempt_count'] == len(latest) and census['incomplete_attempts'] == 0,
         'RESEARCH_GENERATION_DENOMINATOR')
    selected = latest.get(proposal['ledger_attempt_id'])
    need(selected is not None and selected['state'] == 'COMPLETE'
         and selected['candidate_id'] == proposal['candidate_id']
         and selected['strategy_digest'] == proposal['strategy_definition_sha256'], 'RESEARCH_SELECTED_ATTEMPT')
    cross = {'COMPLETE':'SELECTED','INVALID':'REJECTED','FAILED':'FAILED','ABANDONED':'REJECTED'}
    factory_states = {'FAILED','INELIGIBLE','NOT_VERIFIED','QUARANTINED','REJECTED','SELECTED','UNKNOWN','UNSCANNED'}
    expected_states = Counter(cross[e['state']] for e in latest.values())
    need(set(generation['factory_attempt_states']) == factory_states
         and all(type(generation['factory_attempt_states'][k]) is int and
                 generation['factory_attempt_states'][k] == expected_states[k]
             for k in generation['factory_attempt_states']), 'RESEARCH_FACTORY_GENERATION_CENSUS')

    completed, registry_head = ledger(registry)
    record_ids = [r['attempt'] for r in trial['records'].values()]
    attempt_ids = [r['attempt_id'] for r in variants['attempts']]
    need(len(record_ids) == len(set(record_ids)) == len(attempt_ids) == len(set(attempt_ids)) ==
         proposal['frozen_trial_budget'] == variants['attempt_count']
         and set(record_ids) == set(attempt_ids) == set(completed)
         and set(trial['records']) == set(registration['query_pins'])
         and all(e['state'] == 'COMPLETE' for e in completed.values()), 'RESEARCH_VARIANT_POPULATION')
    need(trial['registry']['head_digest'] == registry_head and
         trial['registry']['entry_count'] == len(registry) and
         trial['registry']['total_attempts'] == len(completed) and
         trial['registry']['incomplete_attempts'] == 0 and
         trial['registry']['by_state'] == {k:sum(e['state']==k for e in completed.values()) for k in STATES},
         'RESEARCH_TRIAL_REGISTRY_PARENT')
    attempts = {r['attempt_id']:r for r in variants['attempts']}
    scheduled = {r['attempt_id']:r['reason'] for r in registry if r['state']=='REGISTERED'}
    unknown_signals = unknown_outcomes = modeled = 0
    for label, row in trial['records'].items():
        entry = completed[row['attempt']]
        c = row['cohort']
        need(entry['reason'] == '' and row['attempt'] in attempts and scheduled[row['attempt']] == label
             and entry['candidate_id'] == proposal['candidate_id']
             and entry['strategy_digest'] == proposal['strategy_definition_sha256']
             and entry['search_plan_digest'] == registration['sha256']
             and entry['nomination_digest'] == proposal['nomination_evidence_sha256']
             and attempts[row['attempt']]['candidate_id'] == proposal['candidate_id']
             and attempts[row['attempt']]['source_receipt_sha256'] == row['hashes']['package_sha256'],
             'RESEARCH_VARIANT_RESULT_PARENT')
        need(set(row['hashes']) == {'package_sha256','result_sha256','scientific_lab_sha256','trade_ledger_sha256'}
             and all(type(v) is str and len(v)==64 and set(v)<=set('0123456789abcdef')
                 for v in row['hashes'].values()), 'RESEARCH_RESULT_DIGEST')
        need(all(type(c[k]) is int and c[k]>=0 for k in ('expected_bars','decision_slots','observed_bars',
                 'missing_bars','focus_bar_count','entry_signals','exit_signals','no_signal_bars','signal_unknown',
                 'modeled_trades','unknown_trades'))
             and c['expected_bars'] == c['decision_slots'] == c['observed_bars']+c['missing_bars']
             and c['focus_bar_count'] == c['observed_bars']
             and sum(c[k] for k in ('entry_signals','exit_signals','no_signal_bars','signal_unknown')) == c['decision_slots'],
             'RESEARCH_SCANNER_DENOMINATOR')
        state = 'SELECTED' if c['coverage']=='COMPLETE' else 'UNKNOWN'
        need(attempts[row['attempt']]['state'] == state
             and (state != 'UNKNOWN' or c['modeled_trades']==0 and c['signal_unknown']==c['decision_slots']),
             'RESEARCH_UNKNOWN_PROMOTION')
        unknown_signals += c['signal_unknown']; unknown_outcomes += c['unknown_trades']; modeled += c['modeled_trades']
    for phase, pair in trial['paired'].items():
        base=trial['records'][phase+'/BASE']['cohort'];shadow=trial['records'][phase+'/SHADOW']['cohort']
        need(pair['paired_modeled_outcomes']==base['modeled_trades']==shadow['modeled_trades']
             and pair['unknown_outcomes']==base['unknown_trades']==shadow['unknown_trades'],
             'RESEARCH_PAIRED_DENOMINATOR')
    variant_counts = Counter(a['state'] for a in variants['attempts'])
    need(set(variants['attempt_states']) == factory_states and
         all(type(variants['attempt_states'][k]) is int and variants['attempt_states'][k] == variant_counts[k]
             for k in variants['attempt_states']),
         'RESEARCH_VARIANT_CENSUS')
    need(generation['factory_comparison_trials_status'] == generation['factory_paired_results_status'] == 'NOT_PERFORMED',
         'RESEARCH_GENERATION_TRIAL_CONFLATION')
    return dict(status='RESEARCH_JOIN_PASS',grade='INDEPENDENTLY_VERIFIED_ARTIFACT',
        scope='PERSISTED_ACCEPTED_SYNTHETIC_LINEAGE_ONLY',source_commit=COMMIT,
        attempts=len(latest),trials=1,variants=len(record_ids),
        generation_states=dict(count),factory_generation_receipt_sha256=generation['receipt_sha256'],
        proposal_sha256=proposal['proposal_sha256'],checkpoint_sha256=checkpoint['checkpoint_sha'],
        variant_experiment_sha256=variants['sha256'],trial_result_sha256=trial['sha256'],
        modeled_trade_outcomes=modeled,unknown_signal_slots=unknown_signals,unknown_trade_outcomes=unknown_outcomes,
        raw_inner_h_packages='DIGEST_REFERENCES_ONLY_NOT_REOPENED',
        scientific_acceptance='NOT_GRANTED',trading_authority='NONE',actual_fills=None)
