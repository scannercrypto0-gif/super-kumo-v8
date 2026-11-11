"""Pinned, isolated existing-code ports; no network, orders or private source."""
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from decimal import Decimal


def deny(event,args):
    if event in {'socket.__new__','socket.connect','socket.getaddrinfo','urllib.Request',
                 'subprocess.Popen','os.system'}:
        raise RuntimeError('NETWORK_OR_EXECUTION_FORBIDDEN')


def call(component, action, body):
    if component=='scanner' and action=='admit':
        from tools.scanner_engine_offline.contracts import AdmittedBar,admit_bars
        def dt(ms):return datetime.fromtimestamp(ms/1000,timezone.utc)
        rows=[AdmittedBar(source_id=b['source_id'],timeframe=b['timeframe'],symbol=b['symbol'],
                         open_at=dt(b['open_ms']),close_at=dt(b['open_ms']+body['width_ms']),
                         available_at=dt(b['available_ms']),open=Decimal(str(b['open'])),
                         high=Decimal(str(b['high'])),low=Decimal(str(b['low'])),close=Decimal(str(b['close'])),
                         base_volume=Decimal(str(b['volume'])),quote_volume=Decimal(str(b['volume']*b['close'])))
              for b in body['bars']]
        r=admit_bars(rows,cutoff_at=dt(body['cutoff_ms']),source_id=body['source_id'],availability_class='RETROSPECTIVE_NON_PIT')
        if r.bars_admitted!=len(rows) or r.admission_errors:
            raise ValueError('NATIVE_ADMISSION_REFUSED')
        return {'admitted':r.bars_admitted,'availability_class':r.availability_class}
    if component=='discoverer' and action=='family':
        from tools.strategy_discoverer_offline.families import get_family,family_registry_digest
        from tools.strategy_discoverer_offline.generator import HypothesisGenerator
        family=get_family(body['family_id']);generator=HypothesisGenerator()
        # Existing stateless builders only. run_family's Scanner evidence gate is
        # not invoked for an INDEPENDENT_TEST_ONLY_RESEARCH_SEED; no fake nomination.
        return {'base_spec':generator._build_base_spec(family),
                'axes':generator._build_candidate_grid_axes(family),'family_digest':family.family_digest,
                'family_registry_digest':family_registry_digest(),'max_candidates':family.max_candidates,
                'source_kind':'EXISTING_FAMILY_TEMPLATE_NOT_SCANNER_NOMINATION'}
    if component=='discoverer' and action=='optional_feedback':
        from tools.strategy_discoverer_offline.scanner_adapter import _SCANNER_P0_UNRESOLVED
        if _SCANNER_P0_UNRESOLVED is not True:raise ValueError('QUARANTINE_POLICY_DRIFT')
        return {'status':'UNKNOWN_DEFERRED','required_for_independent_research':False,
                'promotion':'NOT_AUTHORIZED','feedback_sha256':body['feedback_sha256']}
    if component=='factory' and action=='research_handoff':
        from research_wp_r0.strategy_definition import StrategyDefinition
        from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
        from research_wp_r0.aql_factory_research_consumer_seam import seal,build_research_report
        sd=StrategyDefinition.from_dict(body['candidate']['definition'],registry=IndicatorRegistryV2())
        if body['candidate']['source_kind']!='INDEPENDENT_TEST_ONLY_RESEARCH_SEED':raise ValueError('RESEARCH_SOURCE_KIND')
        if body['candidate']['evaluation_status']!='NOT_EVALUATED':raise ValueError('PRECOMPUTED_EVALUATION')
        envelope=body['fixture']['envelope']
        envelope={k:v for k,v in envelope.items() if k!='artifact_sha256'}
        envelope['strategy_version']=sd.digest
        for row in envelope['rows']:row['strategy_version']=sd.digest
        receipt=build_research_report(body['fixture']['schedule'],seal(envelope),body['fixture']['observations'])
        return {'schema':'aql.work.independent-factory-handoff.v1','candidate_digest':body['candidate_digest'],
                'strategy_definition_digest':sd.digest,'receipt':receipt,
                'strategy_rule_trigger_evaluation':'NOT_PERFORMED',
                'evaluation_kind':'EXISTING_FACTORY_TEST_ONLY_DESCRIPTIVE_FIXTURE',
                'authentic_evaluation':'NOT_CONNECTED','paper_registry_promotion':'NOT_AUTHORIZED'}
    raise ValueError('UNSUPPORTED_PINNED_PORT')


if __name__=='__main__':
    component,action,root=sys.argv[1:]
    sys.path.insert(0,str(Path(root).resolve()))
    sys.addaudithook(deny)
    body=json.loads(sys.stdin.buffer.read(8*1024*1024+1))
    result=call(component,action,body)
    sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False))
