"""Strategy-owned ACCEPT/REJECT/WAIT contract. No paper execution consumer exists."""
from dataclasses import asdict
from src.aql.observation.contracts import PaperIntent
from .common import Frozen, digest, require


class TestOnlyStrategySink:
    """Explicit local TEST_ONLY consumer with readback/idempotence, never orders."""
    mode='TEST_ONLY'

    def __init__(self, strategy_spec, journal, decide, *, decision_policy_id):
        self.spec=strategy_spec
        self.journal=journal
        self.decide=decide
        self.decision_policy_id=decision_policy_id

    def receive(self, nomination, delivery_id):
        n=nomination.data;s=self.spec.data
        require(n['strategy_id']==s['strategy_id'] and n['strategy_version']==s['strategy_version']
                and n['config_digest']==s['config_digest'],'WRONG_STRATEGY_ROUTE')
        claim={'schema':'aql.paper-strategy-test-consumer.claim.v1','nomination_sha256':nomination.sha256,
               'strategy_config':s['config_digest'],'decision_policy_id':self.decision_policy_id}
        self.journal.put('claim',delivery_id,claim)
        prior=self.journal.get('result',delivery_id)
        if prior is not None:return Frozen.restore(prior)
        decision=self.decide(n)
        require(decision in ('ACCEPT','REJECT','WAIT'),'STRATEGY_DECISION_ENUM')
        intent=None
        if decision in ('ACCEPT','REJECT'):
            intent=asdict(PaperIntent(nomination.sha256,delivery_id,
                                     'proposed' if decision=='ACCEPT' else 'declined'))
        receipt=Frozen.build({'schema':'aql.paper-strategy-decision-receipt.v1','delivery_id':delivery_id,
            'nomination_sha256':nomination.sha256,'attempt_id':n['attempt_id'],
            'strategy_id':s['strategy_id'],'strategy_version':s['strategy_version'],
            'config_digest':s['config_digest'],'decision':decision,'decision_owner':'STRATEGY_TEST_ONLY_CONSUMER',
            'decision_policy_id':self.decision_policy_id,'paper_intent_interface':intent,
            'consumer_status':'TEST_ONLY_SINK','paper_execution':'NOT_ACTIVATED','trading_authority':'NONE'})
        self.journal.put('result',delivery_id,receipt.receipt())
        return receipt


def route(nomination_receipt, strategy_spec, journal, *, test_sink=None):
    nomination=Frozen.restore(nomination_receipt)
    from .screening import StrategyScreeningSpec
    strategy_spec=StrategyScreeningSpec.restore_spec(strategy_spec.receipt())
    n=nomination.data;s=strategy_spec.data
    require(n['schema']=='aql.strategy-nomination.v1','NOMINATION_SCHEMA')
    require(n['strategy_id']==s['strategy_id'] and n['strategy_version']==s['strategy_version']
            and n['config_digest']==s['config_digest'],'WRONG_STRATEGY_ROUTE')
    require(n['strategy_definition_digest']==s['definition']['digest'] and
            n['feature_snapshot_sha256']==digest(n['feature_evidence']),'NOMINATION_IDENTITY_DRIFT')
    require(n['trading_authority']=='NONE' and n['publishable'] is False
            and n['delivery_authorized'] is False,'NOMINATION_AUTHORITY')
    if test_sink is not None:
        require(type(test_sink) is TestOnlyStrategySink and
                test_sink.spec.data['config_digest']==s['config_digest'],'WRONG_STRATEGY_ROUTE')
    target_policy='NOT_CONNECTED' if test_sink is None else test_sink.decision_policy_id
    delivery_id=digest({'nomination':nomination.sha256,'strategy':s['config_digest'],
                        'consumer_policy':target_policy,
                        'contract':'aql.paper-strategy-handoff.v1'})
    claim={'schema':'aql.paper-strategy-handoff.v1','delivery_id':delivery_id,
           'nomination_sha256':nomination.sha256,'strategy_config':s['config_digest'],
           'consumer_mode':'NOT_CONNECTED' if test_sink is None else 'TEST_ONLY'}
    journal.put('claim',delivery_id,claim)
    prior=journal.get('result',delivery_id)
    if prior is not None:return Frozen.restore(prior)
    if test_sink is None or n['status']!='SELECTED' or n['evidence_class']!='TEST_ONLY':
        result=Frozen.build({**claim,'decision':'WAIT','decision_owner':'NO_CONNECTED_CONSUMER',
             'consumer_status':'PAPER_CONSUMER_NOT_CONNECTED' if test_sink is None else 'NOMINATION_NOT_ELIGIBLE',
             'paper_execution':'NOT_ACTIVATED','trading_authority':'NONE'})
    else:
        require(type(test_sink) is TestOnlyStrategySink and test_sink.mode=='TEST_ONLY','REAL_CONSUMER_FORBIDDEN')
        result=test_sink.receive(nomination,delivery_id)
    journal.put('result',delivery_id,result.receipt())
    return result
