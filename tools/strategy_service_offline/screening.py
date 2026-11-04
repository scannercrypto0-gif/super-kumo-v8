"""Strategy-addressed screening over admitted TEST_ONLY bytes, never trade decisions."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import math
from types import SimpleNamespace
from research_wp_r0.strategy_definition import StrategyDefinition, identifier, integer, number
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2, _read, _test_predicate, _channel, reference_digest
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2, SPECS
from .common import Frozen, canonical, decode, digest, raw_sha, require, BoundaryError

TF = {'5m':300000,'30m':1800000,'1h':3600000,'4h':14400000,'1d':86400000}
STATES = ('SELECTED','REJECTED','UNKNOWN','UNSCANNED','INELIGIBLE','FAILED')
KERNELS = {'SMA_v1','EMA_v1','RSI_v1','ATR_v1'} | {s[0] for s in SPECS}


class StrategyScreeningSpec(Frozen):
    @classmethod
    def from_existing(cls, definition, dna, *, timeframe, market, max_source_age_ms,
                      ranking_channel=None):
        v1=StrategyDefinition.from_dict(definition,registry=IndicatorRegistryV2())
        parsed=StrategyDNAV2(dna['dna'],v1_definition=v1)
        require(parsed.digest==dna['digest'],'DNA_CONFIG_DRIFT')
        require(parsed.spec['strategy_id']==v1.spec['strategy_id'] and
                parsed.spec['strategy_version']==v1.spec['strategy_version'],'STRATEGY_DNA_IDENTITY')
        require(timeframe in TF and type(market) is str and bool(market),'MARKET_TIMEFRAME')
        integer(max_source_age_ms,1,86400000)
        require(all(r['indicator_id'] in KERNELS for r in parsed.spec['indicators']),
                'INDICATOR_TEST_KERNEL_NOT_CONNECTED')
        if ranking_channel is not None:
            require(ranking_channel['mandatory']==[] and ranking_channel['threshold']==0,
                    'RANKING_IS_NOT_A_DECISION_GATE')
            # Reuse the frozen native weighted-channel validator and arithmetic.
            d=parsed.spec;d['decision_profile']['entry']=deepcopy(ranking_channel)
            StrategyDNAV2(d,v1_definition=v1)
        value={'schema':'aql.strategy-screening-spec.v1','strategy_id':v1.spec['strategy_id'],
               'strategy_version':v1.spec['strategy_version'],'definition':v1.to_dict(),
               'dna':{'dna':parsed.spec,'digest':parsed.digest},'timeframe':timeframe,
               'market':market,'max_source_age_ms':max_source_age_ms,'fail_closed':'UNKNOWN',
               'weighted_ranking':ranking_channel,'paper_approval':'NOT_FOUND',
               'scope':'TEST_ONLY_UNAPPROVED_POLICY'}
        value['config_digest']=digest(value)
        return cls.build(value)

    @classmethod
    def restore_spec(cls, receipt):
        raw=Frozen.restore(receipt).data
        obj=cls.from_existing(raw['definition'],raw['dna'],timeframe=raw['timeframe'],market=raw['market'],
                              max_source_age_ms=raw['max_source_age_ms'],ranking_channel=raw['weighted_ranking'])
        require(obj.data==raw,'SPEC_VERSION_OR_POLICY_DRIFT')
        return obj


def registry_snapshot(specs):
    require(0<len(specs)<=16,'STRATEGY_BUDGET')
    ids=[(s.data['strategy_id'],s.data['strategy_version']) for s in specs]
    require(len(ids)==len(set(ids)),'DUPLICATE_STRATEGY')
    return Frozen.build({'schema':'aql.strategy-screening-registry-snapshot.v1',
                         'entries':[s.receipt() for s in sorted(specs,key=lambda x:x.data['strategy_id'])],
                         'source':'EXISTING_RESEARCH_DEFINITION_AND_DNA_ADAPTER',
                         'approved_paper_registry':'NOT_CONNECTED','approval_records':[],
                         'execution_authority':'NONE'})


def admission(raw, manifest, universe, cutoff, timeframe, market):
    """All-or-nothing affected symbol windows. No sorting/filter/salvage-scoring."""
    require(type(cutoff) is int and cutoff>=0,'CUTOFF_TYPE')
    require(universe['cutoff_ms']==manifest['cutoff_ms']==cutoff,'UNIVERSE_MANIFEST_CUTOFF')
    require(manifest['schema']=='aql.strategy-service.source.v1','SOURCE_VERSION')
    members=universe['members']
    require(0<len(members)<=256 and len({m['symbol'] for m in members})==len(members),'UNIVERSE_IDENTITY')
    require(universe['count_unit']=='SYMBOL' and universe['source_raw_sha256']==manifest['raw_sha256'],
            'UNIVERSE_SOURCE_BINDING')
    unknown={m['symbol']:'SOURCE_UNVERIFIED' for m in members}
    if type(raw) is not bytes:
        return {},unknown,'ORIGINAL_SOURCE_BYTES_NOT_AVAILABLE'
    # A self-reported hash/verifier boolean never enables real admission.
    if manifest['evidence_class']!='TEST_ONLY' or universe['evidence_class']!='TEST_ONLY':
        return {},unknown,'REAL_SOURCE_VERIFIER_NOT_CONNECTED'
    if raw_sha(raw)!=manifest['raw_sha256']:
        return {},{m['symbol']:'ORIGINAL_SOURCE_BYTES_MISMATCH' for m in members},'SOURCE_TAMPER'
    try:source=decode(raw)
    except ValueError:return {},unknown,'INVALID_SOURCE_ENCODING'
    require(source['schema']=='aql.strategy-service.synthetic-bars.v1' and
            source['source_id']==manifest['source_id'] and
            source['generation_id']==manifest['generation_id'],'RAW_SOURCE_IDENTITY')
    rows=source['rows'];require(type(rows) is list and len(rows)<=8192,'BAR_BUDGET')
    require(manifest['timeframe']==timeframe and manifest['market']==market,'SOURCE_SCOPE')
    width=TF[timeframe]
    buckets={m['symbol']:[] for m in members}
    for row in rows:
        if row.get('symbol') not in buckets:
            return {},{m['symbol']:'FOREIGN_SYMBOL_IN_SOURCE' for m in members},'SOURCE_IDENTITY'
        buckets[row['symbol']].append(row)
    valid,errors={},{}
    for member in members:
        symbol=member['symbol'];bars=buckets[symbol];reason=None
        if not bars: reason='MISSING_SOURCE_WINDOW'
        for i,b in enumerate(bars):
            if b.get('source_id')!=manifest['source_id'] or b.get('timeframe')!=timeframe:
                reason='MIXED_SOURCE_OR_TIMEFRAME';break
            if b.get('finalized') is not True:reason='NONFINAL_SOURCE';break
            if any(type(b.get(k)) is not int for k in ('open_ms','close_ms','available_ms')):
                reason='UNKNOWN_SOURCE_AVAILABILITY';break
            if not (b['open_ms']%width==0 and b['close_ms']==b['open_ms']+width-1 and
                    b['close_ms']<b['available_ms']<=cutoff):
                reason='FUTURE_OR_INVALID_BAR_CLOCK';break
            if i and b['open_ms']!=bars[i-1]['open_ms']+width:
                reason='DUPLICATE_GAP_OR_UNORDERED_SOURCE';break
            values=[b.get(k) for k in ('open','high','low','close','volume')]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                reason='INVALID_OHLCV';break
            o,h,l,c,v=values
            if l<=0 or not l<=o<=h or not l<=c<=h or v<0:
                reason='INVALID_OHLCV';break
        if bars and reason is None:
            if (bars[0]['open_ms']!=manifest['start_ms'] or
                bars[-1]['close_ms']+1!=manifest['end_exclusive_ms'] or
                len(bars)!=(manifest['end_exclusive_ms']-manifest['start_ms'])//width):
                reason='INCOMPLETE_DECLARED_WINDOW'
        if reason:errors[symbol]=reason
        else:valid[symbol]=bars
    return valid,errors,'TEST_ONLY_ORIGINAL_BYTE_INTEGRITY'


def scan(specs, raw, manifest, universe, *, cutoff_ms, symbol_budget, deps):
    specs=[StrategyScreeningSpec.restore_spec(s.receipt()) for s in specs]
    registry=registry_snapshot(specs)
    integer(symbol_budget,1,256)
    require(len({s.data['timeframe'] for s in specs})==len({s.data['market'] for s in specs})==1,
            'SINGLE_SHARED_SOURCE_SCOPE_REQUIRED')
    tf,market=specs[0].data['timeframe'],specs[0].data['market']
    valid,errors,source_status=admission(raw,manifest,universe,cutoff_ms,tf,market)
    run_id=digest({'registry':registry.sha256,'manifest':manifest,'universe':universe,
                   'cutoff_ms':cutoff_ms,'symbol_budget':symbol_budget})
    ordered=sorted(universe['members'],key=lambda m:m['symbol'])
    for m in ordered:
        require(m['eligible'] in (True,False,None) and type(m['eligible']) in (bool,type(None)), 'ELIGIBILITY_TYPE')
    selected=[m['symbol'] for m in ordered if m['eligible'] is True and
              type(m.get('membership_available_ms')) is int and
              0<=m['membership_available_ms']<=cutoff_ms][:symbol_budget]
    cache={};native_calls=0;compute_calls=0;native_errors={}
    # Every eligible symbol admitted once; indicator calculation shared across policies.
    for symbol in selected:
        if symbol not in valid:continue
        try:
            deps.call('scanner','admit',{'bars':valid[symbol],'width_ms':TF[tf],
                      'cutoff_ms':cutoff_ms,'source_id':manifest['source_id']})
            native_calls+=1
        except ValueError:
            native_errors[symbol]='NATIVE_CONTRACT_ADMISSION_FAILED'
    rows=[]
    for spec_obj in sorted(specs,key=lambda s:s.data['strategy_id']):
        s=spec_obj.data;dna=s['dna']['dna'];refs={r['name']:r for r in dna['indicators']}
        eligible=[];strategy_rows=[]
        for member in ordered:
            symbol=member['symbol'];state='REJECTED';reasons=[];features={};rank=[];score=None
            if type(member.get('membership_available_ms')) is not int or not 0<=member['membership_available_ms']<=cutoff_ms:
                state='UNKNOWN';reasons=['UNIVERSE_MEMBERSHIP_NOT_AVAILABLE']
            elif member['eligible'] is False:state='INELIGIBLE';reasons=['UNIVERSE_INELIGIBLE']
            elif member['eligible'] is None:state='UNKNOWN';reasons=['ELIGIBILITY_UNKNOWN']
            elif source_status!='TEST_ONLY_ORIGINAL_BYTE_INTEGRITY':state='UNKNOWN';reasons=[source_status]
            elif symbol not in selected:state='UNSCANNED';reasons=['SYMBOL_BUDGET']
            elif symbol in errors:state='UNKNOWN';reasons=[errors[symbol]]
            elif symbol in native_errors:state='UNKNOWN';reasons=[native_errors[symbol]]
            elif (cutoff_ms-valid[symbol][-1]['close_ms']-1)>s['max_source_age_ms']:
                state='UNKNOWN';reasons=['STALE_SOURCE_WINDOW']
            elif symbol not in dna['scanner_profile']['allowed_symbols'] or market not in dna['scanner_profile']['allowed_venues']:
                state='INELIGIBLE';reasons=['STRATEGY_SCOPE']
            else:
                try:
                    for name,ref in refs.items():
                        key=(manifest['raw_sha256'],symbol,tf,ref['indicator_id'],digest(ref['parameters']))
                        if key not in cache:
                            ind=IndicatorRegistryV2().get(ref['indicator_id'],**ref['parameters'])
                            bars=valid[symbol]
                            typed=[SimpleNamespace(**b) for b in bars]
                            if hasattr(ind,'_compute_values'):
                                values=ind._compute_values([b['close'] for b in bars],typed)
                                value=values[-1] if len(bars)>ind.min_warmup_bars else None
                                mapped={'value':value}
                            else:
                                vectors=ind._values(typed)
                                values=vectors[-1][1] if vectors and vectors[-1][0]==len(bars)-1 else None
                                mapped=dict(zip(ind.output_fields,values)) if values is not None else {f:None for f in ind.output_fields}
                            for value in mapped.values():
                                if value is not None:number(value)
                            cache[key]=mapped;compute_calls+=1
                        mapped=cache[key]
                        features[name]={'indicator_digest':reference_digest(ref),'source_kind':'SYNTHETIC',
                            'source_id':manifest['source_id'],
                            'source_generation_id':manifest['generation_id'],
                            'original_source_sha256':manifest['raw_sha256'],
                            'quality':'VALID' if all(v is not None for v in mapped.values()) else 'MISSING','is_final':True,
                            'as_of_ms':valid[symbol][-1]['close_ms'],
                            'observed_at_ms':valid[symbol][-1]['available_ms'],
                            'available_at_ms':valid[symbol][-1]['available_ms'],'values':mapped}
                    def read(item):
                        return _read(features,item,refs[item['reference']],dna['provenance'],cutoff_ms)
                    reads=[read(rule) for rule in dna['scanner_profile']['filters']]
                    ranks=[read(term) for term in dna['scanner_profile']['ranking']]
                    if any(r['status']!='AVAILABLE_SYNTHETIC' for r in reads+ranks):
                        state='UNKNOWN';reasons=['MISSING_STALE_OR_UNKNOWN_FEATURE']
                    elif not all(_test_predicate(rule,r) for rule,r in zip(dna['scanner_profile']['filters'],reads)):
                        state='REJECTED';reasons=['STRATEGY_HARD_GATE']
                    else:
                        state='SELECTED'
                        if s['weighted_ranking'] is not None:
                            weighted=_channel(s['weighted_ranking'],read)
                            if weighted['score'] is None:
                                state='UNKNOWN';reasons=['RANKING_UNAVAILABLE']
                            else:score=weighted['score'];rank=[-score]
                        else:
                            rank=[-r['value'] if t['direction']=='DESC' else r['value']
                                  for t,r in zip(dna['scanner_profile']['ranking'],ranks)]
                except (ValueError,KeyError,TypeError,ArithmeticError):
                    state='FAILED';reasons=['FEATURE_COMPUTATION_FAILED'];features={}
            row={'schema':'aql.strategy-nomination.v1','run_id':run_id,'strategy_id':s['strategy_id'],
                 'strategy_version':s['strategy_version'],'config_digest':s['config_digest'],
                 'strategy_definition_digest':s['definition']['digest'],'symbol':symbol,'timeframe':tf,
                 'market':market,'cutoff_ms':cutoff_ms,'source_raw_sha256':manifest['raw_sha256'],
                 'source_manifest_sha256':digest(manifest),'universe_sha256':digest(universe),
                 'feature_evidence':features,'feature_snapshot_sha256':digest(features),
                 'status':state,'reason_codes':reasons,'strategy_screening_rank_score':score,
                 'research_profile_score':None,'evidence_class':'TEST_ONLY',
                 'paper_registry_status':'NOT_CONNECTED','trading_authority':'NONE',
                 'publishable':False,'delivery_authorized':False}
            row['attempt_id']=digest({'run':run_id,'strategy':s['config_digest'],'symbol':symbol})
            strategy_rows.append(row)
            if state=='SELECTED':eligible.append((rank,symbol,row))
        eligible.sort(key=lambda x:(x[0],x[1]))
        for i,(_,symbol,row) in enumerate(eligible):
            if i>=dna['scanner_profile']['max_candidates']:
                row['status']='REJECTED';row['reason_codes']=['STRATEGY_CAPACITY_EXCLUDED']
        counts=Counter(r['status'] for r in strategy_rows)
        census={st.lower():counts[st] for st in STATES}
        require(sum(census.values())==len(ordered),'STRATEGY_DENOMINATOR')
        for row in strategy_rows:
            row['strategy_census']=census
            row['denominator']=len(ordered)
            rows.append(Frozen.build(row).receipt())
    return Frozen.build({'schema':'aql.strategy-aware-scan-run.v1','run_id':run_id,
                         'registry':registry.receipt(),'source_status':source_status,'nominations':rows,
                         'native_symbol_admissions':native_calls,'unique_feature_computations':compute_calls,
                         'source_symbols_considered':len(selected),'authentic_route':'NOT_CONNECTED',
                         'paper_activation':'NOT_AUTHORIZED','trade_decisions':'NOT_MADE_BY_SCANNER'})
