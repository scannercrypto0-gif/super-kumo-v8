"""Isolated read-only contract calls into an explicitly pinned offline checkout.

Only the Core TEST_ONLY fixture stager writes, under a disposable temporary root.
No Scanner scan, feature compute, Discoverer search, Factory evaluator or private run.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
from datetime import datetime


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def no_network(event, args):
    if event in {'socket.__new__', 'socket.connect', 'socket.getaddrinfo',
                 'urllib.Request', 'subprocess.Popen', 'os.system'}:
        raise RuntimeError('NETWORK_OR_CHILD_PROCESS_FORBIDDEN')


def call(action, body):
    if action == 'core':
        from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager, export_archive_query
        from research_wp_r0.aql_core_research_query_seam_v1 import query_custody
        from research_wp_r0.historical_library import HistoricalLibrary
        raw = bytes.fromhex(body['source_hex'])
        assert body['spec']['test_only'] is True
        packet = export_archive_query(raw, expected_source_sha256=body['source_sha256'],
                                      expected_inventory_hash=body['inventory_sha256'], spec=body['spec'])
        library = HistoricalLibrary()
        with tempfile.TemporaryDirectory(prefix='aql-test-only-seam-') as temp:
            stager = OfflineBridgeStager(temp)
            key = stager.stage(packet, raw)
            stager.advance(key, batch_size=256)
            registration = stager.commit(key, library)
            results = [query_custody(library, request) for request in body['requests']]
            from research_wp_r0.aql_core_factory_work_compat_v1 import compatibility_evidence
            compatibility = [compatibility_evidence(library, packet, raw, registration,
                {**request, 'start_ms': body['spec']['start_ms'],
                 'end_exclusive_ms': body['spec']['end_exclusive_ms'],
                 'require_complete': False, 'confirmed_only': False})
                for request in body['requests'] if request['confirmed_only'] is False]
        return {'packet_sha256': key, 'registration': registration, 'queries': results,
                'compatibility': compatibility}
    if action == 'factory':
        from research_wp_r0.aql_factory_research_consumer_seam import build_research_handoff
        from research_wp_r0.aql_factory_cross_owner_compatibility import validate_core_query
        for request, response in body['queries']:
            validate_core_query(request, response)
        return build_research_handoff(body['schedule'], body['envelope'])
    if action == 'scanner':
        from tools.scanner_engine_offline.contracts import ScannerNominationEnvelope
        from tools.scanner_engine_offline.evidence import EvidenceReceipt, _claim_receipt_id
        e = body['envelope']
        constructor = {k:v for k,v in e.items() if k not in ('schema_version', 'digest')}
        constructor['cutoff_at'] = datetime.fromisoformat(e['cutoff_at'])
        envelope = ScannerNominationEnvelope(**constructor).seal()
        if envelope.as_dict() != e:
            raise ValueError('SCANNER_NATIVE_ENVELOPE_DIGEST')
        r = dict(body['receipt'])
        r.pop('schema_version')
        r['payload'] = e
        r['claim_at'] = datetime.fromisoformat(r['claim_at'])
        r['committed_at'] = datetime.fromisoformat(r['committed_at'])
        receipt = EvidenceReceipt(**r)
        if not receipt.verify_integrity():
            raise ValueError('SCANNER_NATIVE_RECEIPT_DIGEST')
        expected = _claim_receipt_id(r['scanner_id'], r['symbol'], r['profile'],
                                     r['claim_at'], body['run_id'])
        if expected != r['receipt_id']:
            raise ValueError('SCANNER_NATIVE_RECEIPT_ID')
        return {'envelope': envelope.as_dict(), 'receipt': receipt.as_dict(),
                'producer_scan': 'NOT_CALLED', 'score': 'NOT_COMPUTED'}
    if action == 'discoverer':
        from tools.strategy_discoverer_offline.scanner_adapter import (
            RawScannerEnvelope, ScannerQuarantineAdapter, assert_eligible_for_research,
            _SCANNER_P0_UNRESOLVED,
        )
        if _SCANNER_P0_UNRESOLVED is not True:
            raise ValueError('SCANNER_QUARANTINE_POLICY_DRIFT')
        args = dict(body)
        args['envelope_payload_bytes'] = bytes.fromhex(args.pop('envelope_hex'))
        args['receipt_payload_bytes'] = bytes.fromhex(args.pop('receipt_hex'))
        admitted = ScannerQuarantineAdapter().admit(RawScannerEnvelope(**args))
        if admitted.evidence is None:
            raise ValueError('DISCOVERER_NATIVE_ADMISSION:' + admitted.quarantine)
        try:
            assert_eligible_for_research(admitted.evidence)
            eligible = True
        except ValueError:
            eligible = False
        if eligible or admitted.quarantine != 'UNKNOWN_DEFERRED':
            raise ValueError('QUARANTINE_PROMOTION')
        return {'evidence': admitted.evidence.to_dict(), 'eligible': eligible,
                'quarantine': admitted.quarantine, 'reason': admitted.reason,
                'candidate_generation': 'NOT_CALLED', 'factory_routing': 'NOT_CONNECTED'}
    raise ValueError('UNKNOWN_WORKER_ACTION')


if __name__ == '__main__':
    # Python -I excludes ambient PYTHONPATH; only the explicit component is added.
    action, root = sys.argv[1:]
    sys.path.insert(0, str(Path(root).resolve()))
    sys.addaudithook(no_network)
    body = json.loads(sys.stdin.buffer.read(8 * 1024 * 1024 + 1))
    sys.stdout.buffer.write(canonical(call(action, body)))
