"""TEST_ONLY source-open bridge regression; original windows remain immutable."""
from copy import deepcopy
from hashlib import sha256
from decimal import Decimal
import json, unittest
from test_aql_p2_factory_modeled_trades import fixture,seal
from research_wp_r0.aql_p2_factory_lab import LabContractError,digest
from research_wp_r0.aql_p2_factory_modeled_trades import build_modeled_trade_package,render_research_report

def inputs():
    s,p,c,w,d=fixture(both_trigger=True);rows=[]
    for bar in w[0]['bars']:
        row={k:v for k,v in bar.items() if k!='content_sha256'}
        row.update(dataset_id=s['source']['source_id'],source_archive_sha256=s['source']['source_package_sha256'],
          is_final=True,finality='ARCHIVED_CLOSED_INTERVAL',historical_known_at_ms=None,historical_receipt_ms=None,historical_publication_ms=None)
        def raw(obj):return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
        row['bar_sha256']=sha256(raw(row)).hexdigest();rows.append(row)
    normal=sha256(b''.join(raw(r) for r in rows)).hexdigest();s['source'].update(normalized_sha256=normal);s['source_bar_count']=len(rows)
    pin=p['full_protocol']['source_pins'][s['source']['source_id']]
    pin.update(start_ms=rows[0]['open_ms'],end_exclusive_ms=rows[-1]['close_ms']+1,dataset_normalized_sha256=normal)
    p['source_normalized_sha256']=normal
    s['protocol']['preregistration_sha256']=digest(p['full_protocol']);p['preregistration_sha256']=s['protocol']['preregistration_sha256']
    for bar,row in zip(w[0]['bars'],rows):bar.pop('open');bar['content_sha256']=row['bar_sha256']
    seal(w[0],'source_window_sha256');seal(s);seal(p);c['preregistration_sha256']=p['artifact_sha256'];seal(c)
    return (s,p,c,w,d),rows

class SourceOpenBridge(unittest.TestCase):
    def run_it(self,i,r):
        from research_wp_r0.aql_p2_factory_modeled_trades import WORK_SOURCE_PROOF_SHA,CORE_PREOUTCOME_ANCHOR_RAW_SHA,WORK_WINDOWS_DELIVERY_RECEIPT_SHA
        return build_modeled_trade_package(*i,provenance_verified=True,prereg_time_verified=True,source_rows=r,
          source_proof_sha256=WORK_SOURCE_PROOF_SHA,prereg_anchor_raw_sha256=CORE_PREOUTCOME_ANCHOR_RAW_SHA,
          windows_delivery_receipt_sha256=WORK_WINDOWS_DELIVERY_RECEIPT_SHA)
    def test_actual_original_window_shape_without_open(self):
        i,r=inputs();before=deepcopy(i);result=self.run_it(i,r)
        self.assertEqual(i,before);self.assertEqual(result['modeled_trades'][0]['entry_open'],'100')
        row=result['modeled_trades'][0]
        self.assertEqual(Decimal(row['fee_entry_return'])+Decimal(row['fee_exit_return']),Decimal('.002'))
        self.assertEqual(Decimal(row['slippage_entry_return'])+Decimal(row['slippage_exit_return']),Decimal('.001'))
        self.assertIn('regime UNKNOWN',render_research_report([result]))
    def test_tampered_source_open_fails_before_scoring(self):
        i,r=inputs();r[0]['open']='101'
        with self.assertRaisesRegex(LabContractError,'SOURCE_ROW_CONTENT_HASH'):self.run_it(i,r)
    def test_missing_or_cross_cohort_source_fails(self):
        i,r=inputs()
        with self.assertRaisesRegex(LabContractError,'SOURCE_ROW_DENOMINATOR'):self.run_it(i,r[:-1])
        r[0]['dataset_id']='OTHER'
        with self.assertRaisesRegex(LabContractError,'SOURCE_ROW_IDENTITY'):self.run_it(i,r)
    def test_window_source_hash_join_cannot_be_forged(self):
        i,r=inputs();i[3][0]['bars'][0]['content_sha256']='f'*64;seal(i[3][0],'source_window_sha256')
        with self.assertRaisesRegex(LabContractError,'TRADE_WINDOW_OR_SOURCE_OPEN_DRIFT'):self.run_it(i,r)
    def test_forged_full_protocol_self_hash_not_registration(self):
        i,r=inputs();i[1]['full_protocol']['extra']='FORGED';seal(i[1]);i[2]['preregistration_sha256']=i[1]['artifact_sha256'];seal(i[2])
        with self.assertRaisesRegex(LabContractError,'FROZEN_POLICY_SPEC_DIGEST'):self.run_it(i,r)

if __name__=='__main__':unittest.main()
