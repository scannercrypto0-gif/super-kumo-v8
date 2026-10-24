import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.contracts import *
class G2Contracts(unittest.TestCase):
    def ctx(self): return {k:ContextValue(None,None,None,None,'unknown') for k in CONTEXT_KEYS}
    def snap(self,**changes):
        a=dict(opportunity_key='btc:1',source='fixture',event_ms=100,receipt_ms=110,decision_ms=120,
               disposition='rejected',context=self.ctx(),freshness_limit_ms=30)
        a.update(changes); return DecisionSnapshot(**a)
    def test_deterministic(self): self.assertEqual(self.snap().serialized(),self.snap().serialized())
    def test_all_dispositions(self):
        for d in DISPOSITIONS: self.assertEqual(self.snap(disposition=d).disposition,d)
    def test_inverted_time(self):
        with self.assertRaises(ContractError): self.snap(receipt_ms=90)
    def test_future_context(self):
        c=self.ctx();c['btc_eth']=ContextValue('1','feed',100,121)
        with self.assertRaises(ContractError): self.snap(context=c)
    def test_incomplete_context_timestamps_fail_closed(self):
        c=self.ctx();c['btc_eth']=ContextValue('1','feed',100,None)
        with self.assertRaises(ContractError): self.snap(context=c)
    def test_noninteger_clock_fails_closed(self):
        with self.assertRaises(ContractError): self.snap(receipt_ms='110')
        with self.assertRaises(ContractError): self.snap(freshness_limit_ms='30')
    def test_stale_context(self):
        c=self.ctx();c['btc_eth']=ContextValue('1','feed',1,2)
        with self.assertRaises(ContractError): self.snap(context=c)
    def test_missing_reason(self):
        c=self.ctx();c['btc_eth']=ContextValue(None,None,None,None)
        with self.assertRaises(ContractError): self.snap(context=c)
    def test_copy_protected(self):
        c=self.ctx();s=self.snap(context=c);c['btc_eth']=ContextValue('1','feed',100,110)
        self.assertIsNone(s.context['btc_eth'].value)
        with self.assertRaises(TypeError): s.context['btc_eth']=c['btc_eth']
    def test_replay_and_conflict(self):
        l=ObservationLedger();self.assertEqual(l.add_snapshot(self.snap()),'inserted')
        self.assertEqual(l.add_snapshot(self.snap()),'duplicate')
        with self.assertRaises(ContractError): l.add_snapshot(self.snap(disposition='expired'))
    def test_horizons(self):
        l=ObservationLedger();s=self.snap();l.add_snapshot(s)
        for h in HORIZONS_MS:
            self.assertEqual(l.horizon_state(s.snapshot_id,h,s.decision_ms+h),'pending')
            o=Observation(s.snapshot_id,h,s.decision_ms+h,s.decision_ms+h+1,'feed','receipt','up')
            self.assertEqual(l.add_observation(o),'inserted')
            self.assertEqual(l.add_observation(o),'duplicate')
            self.assertEqual(l.horizon_state(s.snapshot_id,h,s.decision_ms+h),'pending')
            self.assertEqual(l.horizon_state(s.snapshot_id,h,s.decision_ms+h+1),'mature')
    def test_missing_invalid(self):
        l=ObservationLedger();s=self.snap();l.add_snapshot(s);h=HORIZONS_MS[0]
        l.add_observation(Observation(s.snapshot_id,h,s.decision_ms+h,s.decision_ms+h,'feed','receipt',None,'gap'))
        self.assertEqual(l.horizon_state(s.snapshot_id,h,s.decision_ms+h),'missing')
        self.assertEqual(l.horizon_state(s.snapshot_id,5,200),'invalid')
    def test_premature(self):
        l=ObservationLedger();s=self.snap();l.add_snapshot(s)
        with self.assertRaises(ContractError): l.add_observation(Observation(s.snapshot_id,HORIZONS_MS[0],200,200,'feed','receipt','up'))
if __name__=='__main__': unittest.main()
