import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.positions import *
DAY=86400000
class PositionTests(unittest.TestCase):
    def e(self,id,kind,t,**kw): return PositionEvent('p1',id,kind,t,t,'fixture',**kw)
    def test_week_and_year_stay_open(self):
        l=PositionLedger();l.append(self.e('open','opened',0))
        self.assertEqual(l.status('p1',8*DAY),'open')
        self.assertEqual(l.status('p1',366*DAY),'open')
        self.assertEqual(l.elapsed_ms('p1',366*DAY),366*DAY)
    def test_72h_does_not_close(self):
        l=PositionLedger();l.append(self.e('open','opened',0))
        p=HorizonPolicy('swing',1,(4*3600000,DAY,3*DAY,7*DAY))
        self.assertEqual(l.checkpoint_state('p1',p,3*DAY,4*DAY),'due')
        self.assertEqual(l.status('p1',4*DAY),'open')
    def test_explicit_close(self):
        l=PositionLedger();l.append(self.e('open','opened',0))
        l.append(self.e('close','closed',8*DAY,reason='policy exit'))
        self.assertEqual(l.status('p1',9*DAY),'closed')
        self.assertEqual(l.elapsed_ms('p1',9*DAY),8*DAY)
        with self.assertRaises(PositionContractError): l.append(self.e('later','quote',10*DAY,price='1'))
    def test_replay_conflict(self):
        l=PositionLedger();e=self.e('open','opened',0);self.assertEqual(l.append(e),'inserted')
        self.assertEqual(l.append(e),'duplicate')
        with self.assertRaises(PositionContractError): l.append(self.e('open','opened',1))
    def test_reorder(self):
        l=PositionLedger();l.append(self.e('open','opened',100))
        with self.assertRaises(PositionContractError): l.append(self.e('older','quote',99,price='2'))
    def test_missing_quote_is_not_fabricated(self):
        l=PositionLedger();l.append(self.e('open','opened',0))
        self.assertEqual(l.status('p1',90*DAY),'open')
        self.assertEqual(len(l.events),1)
    def test_long_term_policy(self):
        p=HorizonPolicy('investor',2,(30*DAY,90*DAY,180*DAY,365*DAY))
        self.assertIn(365*DAY,p.horizons_ms)
    def test_bad_policy(self):
        with self.assertRaises(PositionContractError): HorizonPolicy('x',1,(DAY,DAY))
    def test_closed_requires_reason(self):
        with self.assertRaises(PositionContractError): self.e('c','closed',1)
    def test_future_close_not_visible(self):
        l=PositionLedger();l.append(self.e('open','opened',0))
        l.append(self.e('close','closed',8*DAY,reason='exit'))
        self.assertEqual(l.status('p1',7*DAY),'open')
if __name__=='__main__': unittest.main()
