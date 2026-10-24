"""Independent high-precision formula vectors; no production calculation helpers."""
import dataclasses
from decimal import Decimal, localcontext
import json
import math
import pathlib
import sys
import pytest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from test_sf_ind_01 import _bars,_lib_with as _base_lib,BASE_MS,IMS
from research_wp_r0.historical_library import HistoricalDataError,DataAvailabilityKind
from research_wp_r0.indicator_library import IndicatorLibrary
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2,VectorResult,VectorManifest
PARAMS={"MACD_v2":{"fast":2,"slow":4,"signal":3},"BBANDS_v2":{"period":3,"deviations":2.},
        "ADX_v2":{"period":3},"STOCH_v2":{"period":3,"smooth":2},"ROC_v2":{"period":3},"OBV_v2":{}}


def input_bars():
    prices=[10,11,10,14,12,15,13,13,18,11,10,16]
    return [dataclasses.replace(b,open=float(c),close=float(c),high=float(c+1),low=float(c-1),volume=float(i+1))
            for i,(b,c) in enumerate(zip(_bars(len(prices)),prices))]


def run(name,bars=None,cutoff=None,end=None,**kwargs):
    bars=input_bars() if bars is None else bars
    _,accessor=_lib_with(bars)
    indicator=IndicatorRegistryV2().get(name,**PARAMS[name])
    return indicator.compute(accessor,"BTC1M",BASE_MS,end or bars[-1].bar_open,
                             cutoff or bars[-1].bar_close+1,version=1,**kwargs)


def reference(name,bars):
    D=lambda x:Decimal(str(x))
    c=[D(b.close) for b in bars];hi=[D(b.high) for b in bars];lo=[D(b.low) for b in bars]
    vol=[D(b.volume) for b in bars]
    # Closed-form weighted EMA per prefix, independent of production recurrence.
    def weighted(values,p):
        alpha=Decimal(2)/(p+1);seed=sum(values[:p])/p
        return [seed*(1-alpha)**(j-p+1)+sum(alpha*values[k]*(1-alpha)**(j-k) for k in range(p,j+1))
                for j in range(p-1,len(values))]
    if name=="MACD_v2":
        f=weighted(c,2);s=weighted(c,4)
        line=[f[i+2]-v for i,v in enumerate(s)]
        signal=weighted(line,3)
        return [(i+5,(line[i+2],v,line[i+2]-v)) for i,v in enumerate(signal)]
    if name=="BBANDS_v2":
        out=[]
        for i in range(2,len(c)):
            v=c[i-2:i+1];mean=sum(v)/3
            variance=sum(x*x for x in v)/3-mean*mean
            out.append((i,(mean,mean+2*variance.sqrt(),mean-2*variance.sqrt())))
        return out
    if name=="STOCH_v2":
        ks=[Decimal(100)*(c[i]-min(lo[i-2:i+1]))/(max(hi[i-2:i+1])-min(lo[i-2:i+1]))
            for i in range(2,len(c))]
        return [(i+3,(ks[i+1],(ks[i]+ks[i+1])/2)) for i in range(len(ks)-1)]
    if name=="ROC_v2":
        return [(i,(100*(c[i]-c[i-3])/c[i-3],)) for i in range(3,len(c))]
    if name=="OBV_v2":
        return [(i,(sum(vol[j] if c[j]>c[j-1] else -vol[j] if c[j]<c[j-1] else Decimal(0)
                       for j in range(1,i+1)),)) for i in range(len(c))]
    tr=[];plus=[];minus=[]
    for i in range(1,len(c)):
        up=hi[i]-hi[i-1];down=lo[i-1]-lo[i]
        tr.append(max(hi[i]-lo[i],abs(hi[i]-c[i-1]),abs(lo[i]-c[i-1])))
        plus.append(up if up>max(down,0) else Decimal(0))
        minus.append(down if down>max(up,0) else Decimal(0))
    # Wilder smoothed sums from closed-form decaying weights, not a loop recurrence.
    q=Decimal(2)/3
    def smooth(v,i):
        return sum(v[:3])*q**(i-3)+sum(v[j-1]*q**(i-j) for j in range(4,i+1))
    dis=[];dx=[]
    for i in range(3,len(c)):
        t,p,m=smooth(tr,i),smooth(plus,i),smooth(minus,i)
        a,b=100*p/t,100*m/t
        dis.append((a,b));dx.append(100*abs(a-b)/(a+b) if a+b else Decimal(0))
    out=[]
    for j in range(2,len(dx)):
        a=sum(dx[:3])/3*q**(j-2)+sum(dx[k]/3*q**(j-k) for k in range(3,j+1))
        out.append((j+3,(a,*dis[j])))
    return out


@pytest.mark.parametrize("name",PARAMS)
def test_independent_decimal_reference_vectors(name):
    bars=input_bars();rows,manifest=run(name,bars)
    with localcontext() as ctx:
        ctx.prec=50
        expected=reference(name,bars)
    assert len(rows)==len(expected)
    for row,(index,values) in zip(rows,expected):
        assert row.bar_open_ms==bars[index].bar_open
        assert [v for _,v in row.value]==pytest.approx([float(v) for v in values],rel=1e-10,abs=1e-10)
    assert manifest.verify(rows)


@pytest.mark.parametrize("name",PARAMS)
def test_pit_prefix_future_injection_and_cutoff_hash(name):
    bars=input_bars();last=bars[-1]
    original,_=run(name,bars)
    earlier,_=run(name,bars,cutoff=bars[-2].bar_close+1,end=bars[-2].bar_open)
    assert [r.value for r in earlier]==[r.value for r in original[:len(earlier)]]
    later,_=run(name,bars,cutoff=last.bar_close+60001)
    assert later[-1].provenance_hash!=original[-1].provenance_hash
    with pytest.raises(HistoricalDataError):
        run(name,bars,cutoff=bars[-2].bar_close+1)
    injected=[*bars[:-1],dataclasses.replace(last,observation_cutoff_ms=last.bar_close+60001)]
    with pytest.raises(HistoricalDataError):run(name,injected,cutoff=last.bar_close+1)


@pytest.mark.parametrize("name",PARAMS)
def test_gap_warmup_partial_and_retrospective(name):
    bars=input_bars()
    with pytest.raises(HistoricalDataError):run(name,bars[:5]+bars[6:])
    with pytest.raises(ValueError):run(name,require_complete=False)
    with pytest.raises(HistoricalDataError):run(name,[dataclasses.replace(b,availability_kind=DataAvailabilityKind.RETROSPECTIVE) for b in bars])
    ind=IndicatorRegistryV2().get(name,**PARAMS[name])
    if ind.min_warmup_bars:
        _,accessor=_lib_with(bars)
        rows,manifest=ind.compute(accessor,"BTC1M",BASE_MS,BASE_MS+(ind.min_warmup_bars-1)*IMS,bars[-1].bar_close+1)
        assert rows==[] and manifest.result_count==0


@pytest.mark.parametrize("name",PARAMS)
def test_immutable_roundtrip_tamper_and_determinism(name):
    rows,manifest=run(name);again,m2=run(name)
    assert rows==again and manifest==m2
    serialized=json.loads(json.dumps(rows[-1].to_dict()))
    assert VectorResult.from_dict(serialized)==rows[-1]
    serialized["decision_cutoff_ms"]+=1
    with pytest.raises(ValueError):VectorResult.from_dict(serialized)
    with pytest.raises(dataclasses.FrozenInstanceError):rows[-1].value=()
    md=manifest.to_dict()
    assert VectorManifest.from_dict(md,expected_hash=md["manifest_hash"])==manifest
    md["dataset_version"]=2
    with pytest.raises(ValueError):VectorManifest.from_dict(md,expected_hash=m2.to_dict()["manifest_hash"])


@pytest.mark.parametrize("name",PARAMS)
def test_flat_and_zero_volume_finite(name):
    bars=[dataclasses.replace(b,open=10.,high=10.,low=10.,close=10.,volume=0.) for b in input_bars()]
    rows,_=run(name,bars)
    assert rows
    for r in rows:assert all(math.isfinite(v) for _,v in r.value)
    if name=="STOCH_v2":assert dict(rows[-1].value)=={"k":50.,"d":50.}
    elif name=="ADX_v2":assert dict(rows[-1].value)=={"adx":0.,"plus_di":0.,"minus_di":0.}
    elif name=="OBV_v2":assert dict(rows[-1].value)=={"obv":0.}


@pytest.mark.parametrize("name,params",[("MACD_v2",{"fast":4,"slow":3,"signal":2}),
    ("ROC_v2",{"period":True}),("ADX_v2",{"period":2.0}),("BBANDS_v2",{"period":3,"deviations":float("nan")}),
    ("BBANDS_v2",{"period":3,"deviations":True}),("OBV_v2",{"period":2}),("VWAP_v2",{})])
def test_strict_registry(name,params):
    with pytest.raises((ValueError,KeyError)):IndicatorRegistryV2().get(name,**params)


def test_v1_registry_and_bytes_unchanged():
    new=IndicatorRegistryV2();old=IndicatorLibrary()
    assert set(new.available())==set(old.available())|set(PARAMS)
    _,accessor=_lib_with(input_bars())
    for name in old.available():
        assert new.get(name,period=3).compute(accessor,"BTC1M",BASE_MS,BASE_MS+11*IMS,BASE_MS+12*IMS)==old.get(name,period=3).compute(accessor,"BTC1M",BASE_MS,BASE_MS+11*IMS,BASE_MS+12*IMS)


def test_parameter_provenance_and_zero_denominator():
    rows,m=run("BBANDS_v2")
    _,a=_lib_with(input_bars())
    different,_=IndicatorRegistryV2().get("BBANDS_v2",period=3,deviations=3.).compute(a,"BTC1M",BASE_MS,BASE_MS+11*IMS,BASE_MS+12*IMS)
    assert rows[-1].provenance_hash!=different[-1].provenance_hash
    bars=[dataclasses.replace(b,open=0.,high=1.,low=0.,close=0.) for b in input_bars()]
    # Zero-price data is rejected by historical validation or ROC denominator guard.
    with pytest.raises((ValueError,HistoricalDataError)):run("ROC_v2",bars)


def test_actual_dependency_guard():
    from research_wp_r0._dep_guard import check_file
    assert check_file(pathlib.Path(__file__).resolve().parents[1]/"research_wp_r0/indicator_library_v2.py")==[]


def _lib_with(bars):
    # Fixture custody creation time is explicit: real manifests must not be rewritten.
    with patch("research_wp_r0.historical_library.time.time", return_value=1700000000):
        return _base_lib(bars)

@pytest.mark.parametrize("name",PARAMS)
def test_cross_platform_golden_commitments(name):
    expected=json.loads((pathlib.Path(__file__).parent/"fixtures/sf_ind_02_golden.json").read_text(encoding="utf-8"))[name]
    rows,manifest=run(name)
    assert rows[-1].provenance_hash==expected["result"]
    assert manifest.to_dict()["manifest_hash"]==expected["manifest"]


def test_custody_adapter_is_mandatory():
    with pytest.raises(ValueError,match="CustodyAccessor"):
        IndicatorRegistryV2().get("OBV_v2").compute(object(),"x",0,0,1)


@pytest.mark.parametrize("version", [True, 1.0, 0, -1])
def test_dataset_version_is_strict(version):
    bars=input_bars();_,accessor=_lib_with(bars)
    with pytest.raises(ValueError,match="version"):
        IndicatorRegistryV2().get("OBV_v2").compute(accessor,"BTC1M",BASE_MS,bars[-1].bar_open,bars[-1].bar_close+1,version=version)


def test_corrupt_dataset_manifest_is_rejected():
    bars=input_bars();library,accessor=_lib_with(bars)
    object.__setattr__(library.get_manifest("BTC1M",1),"source_label","corrupt")
    with pytest.raises(ValueError,match="manifest integrity"):
        IndicatorRegistryV2().get("OBV_v2").compute(accessor,"BTC1M",BASE_MS,bars[-1].bar_open,bars[-1].bar_close+1)


def test_manifest_rejects_mixed_result_identity_and_binds_seed_range():
    rows,manifest=run("OBV_v2")
    metadata=manifest.to_dict();metadata.pop("manifest_hash")
    metadata["dataset_id"]="OTHER"
    mixed=VectorManifest.create(metadata,rows)
    assert not mixed.verify(rows)
    metadata=manifest.to_dict();metadata.pop("manifest_hash")
    metadata["output_fields"]=["wrong"]
    assert not VectorManifest.create(metadata,rows).verify(rows)
    bars=input_bars();_,accessor=_lib_with(bars)
    _,later=IndicatorRegistryV2().get("OBV_v2").compute(accessor,"BTC1M",BASE_MS+IMS,bars[-1].bar_open,bars[-1].bar_close+1)
    assert manifest.start_ms==BASE_MS and later.start_ms==BASE_MS+IMS
    assert manifest.input_bar_hash!=later.input_bar_hash
