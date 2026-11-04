"""Independent Discoverer family adapter: existing builders/grid, complete draw ledger.

No Scanner nomination dependency and no false external evidence. The optional
Scanner feedback path remains quarantined and cannot confer research authority.
"""
from collections import Counter
from itertools import product
import json
from research_wp_r0.strategy_definition import StrategyDefinition, AttemptRecorder, candidate_grid
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from .common import Frozen, canonical, digest, raw_sha, require, BoundaryError


def independent_research(plan, journal, deps, *, factory_fixture, optional_scanner_feedback=None):
    require(plan['schema']=='aql.independent-research-plan.v1' and plan['evidence_class']=='TEST_ONLY',
            'AUTHENTIC_RESEARCH_NOT_AUTHORIZED')
    require(type(plan['budget']) is int and 1<=plan['budget']<=256,'PLAN_BUDGET')
    require(0<len(plan['families'])<=7 and len(set(plan['families']))==len(plan['families']),'FAMILY_SELECTION')
    plan_id=digest({'plan_id':plan['plan_id'],'contract':plan['schema']})
    journal.put('claim',plan_id,{'schema':plan['schema'],'frozen_plan':plan,'plan_sha256':digest(plan)})
    prior=journal.get('result',plan_id)
    if prior is not None:return Frozen.restore(prior)
    feedback={'status':'ABSENT_OPTIONAL','required_for_independent_research':False}
    if optional_scanner_feedback is not None:
        feedback=deps.call('discoverer','optional_feedback',{'feedback_sha256':digest(optional_scanner_feedback)})
    native=AttemptRecorder(journal)
    attempts=[];candidates=[];seen={};draw_count=0
    for family_id in plan['families']:
        template=deps.call('discoverer','family',{'family_id':family_id})
        axes=plan.get('test_axes',{}).get(family_id,template['axes'])
        require(type(axes) is dict and set(axes)==set(template['axes']),'FAMILY_AXIS_CONTRACT')
        total=1
        for values in axes.values():
            require(type(values) is list and 0<len(values)<=32,'AXIS_BOUND')
            total*=len(values)
        require(total<=512 and draw_count+total<=512,'PLANNED_ATTEMPT_LIMIT')
        names=sorted(axes)
        draws=product(*(axes[n] for n in names)) if names else [()]
        family_draw=0
        for values in draws:
            draw_count+=1;family_draw+=1
            selected=dict(zip(names,values))
            attempt_id=digest({'plan_sha256':digest(plan),'family':family_id,'draw':family_draw,'parameters':selected})
            claim={'schema':'aql.independent-research-attempt.v1','attempt_id':attempt_id,
                   'plan_sha256':digest(plan),'family_id':family_id,'family_digest':template['family_digest'],
                   'draw_number':draw_count,'parameters':selected,'state':'CLAIMED_BEFORE_VALIDATION'}
            journal.put('claim',attempt_id,claim)
            terminal=journal.get('result',attempt_id)
            if terminal is not None:
                state=terminal['state']
                if state in ('SUBMITTED_NOT_EVALUATED','FACTORY_HANDOFF_BLOCKED'):
                    candidate=Frozen.restore(terminal['candidate']);seen[candidate.data['definition']['digest']]=attempt_id
                    candidates.append(candidate.receipt())
                attempts.append(terminal);continue
            state='INVALID';candidate=None;duplicate_of=None;error=None;handoff=None
            if draw_count>plan['budget'] or family_draw>template['max_candidates']:
                state='BUDGET_EXHAUSTED'
            else:
                try:
                    # The seven families/templates and generation math stay in #230/main.
                    base=StrategyDefinition(template['base_spec'],registry=IndicatorRegistryV2())
                    generated=candidate_grid(base,{n:[selected[n]] for n in names},
                        registry=IndicatorRegistryV2(),maximum=1)[0] if names else base
                    # Existing merged recorder persists PENDING or INVALID before publication.
                    prepared,definition=native.prepare(generated.to_json(),family_id,
                                                       'draw_'+str(draw_count),registry=IndicatorRegistryV2())
                    require(definition.digest==generated.digest,'STRATEGY_REPARSE_DRIFT')
                    if definition.digest in seen:
                        state='DUPLICATE';duplicate_of=seen[definition.digest]
                    else:
                        seen[definition.digest]=attempt_id
                        candidate=Frozen.build({'schema':'aql.independent-research-candidate.v1',
                            'source_kind':'INDEPENDENT_TEST_ONLY_RESEARCH_SEED','scanner_nomination_required':False,
                            'plan_sha256':digest(plan),'family_id':family_id,'family_digest':template['family_digest'],
                            'attempt_id':attempt_id,'definition':definition.to_dict(),
                            'evaluation_status':'NOT_EVALUATED','scientific_acceptance':'NOT_OBTAINED',
                            'paper_registry_promotion':'NOT_AUTHORIZED','trading_authority':'NONE'})
                        try:
                            handoff=deps.call('factory','research_handoff',{'candidate':candidate.data,
                                     'candidate_digest':candidate.sha256,'fixture':factory_fixture})
                            require(handoff['strategy_definition_digest']==definition.digest,'FACTORY_CANDIDATE_DRIFT')
                            state='SUBMITTED_NOT_EVALUATED'
                        except BoundaryError as exc:
                            state='FACTORY_HANDOFF_BLOCKED';error=type(exc).__name__
                except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
                    state='INVALID' if isinstance(exc,(ValueError,TypeError,KeyError)) else 'FAILED'
                    error=type(exc).__name__
            terminal={'schema':'aql.independent-research-attempt-result.v1','attempt_id':attempt_id,
                      'claim_sha256':digest(claim),'state':state,'duplicate_of':duplicate_of,
                      'error_type':error,'candidate':candidate.receipt() if candidate is not None else None,
                      'factory_handoff':handoff}
            journal.put('result',attempt_id,terminal)
            attempts.append(terminal)
            if state in ('SUBMITTED_NOT_EVALUATED','FACTORY_HANDOFF_BLOCKED'):candidates.append(candidate.receipt())
    counts=Counter(a['state'] for a in attempts)
    require(len(attempts)==draw_count and sum(counts.values())==draw_count,'RESEARCH_ATTEMPT_CENSUS')
    result=Frozen.build({'schema':'aql.independent-discoverer-research-run.v1','plan_sha256':digest(plan),
        'source_kind':'INDEPENDENT_TEST_ONLY_RESEARCH_SEED','scanner_required':False,'optional_feedback':feedback,
        'attempts':attempts,'attempt_count':draw_count,'status_counts':dict(sorted(counts.items())),
        'unique_definitions':len(candidates),'candidates':candidates,
        'authentic_factory_evaluation':'NOT_CONNECTED','strategy_semantic_evaluation':'NOT_PERFORMED',
        'scientific_acceptance':'NOT_OBTAINED','paper_registry_promotion':'NOT_AUTHORIZED'})
    journal.put('result',plan_id,result.receipt())
    return result
