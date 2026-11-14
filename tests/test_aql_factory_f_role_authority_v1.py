"""Factory F4 independent role authorization suite; contract-only test keys."""
import copy
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from research_wp_r0.aql_factory_f_role_authority_v1 import (
    verify_role_attestations,ResultsStoreError,ROLES,SCHEMA,
)

class TestFactoryFRoleAuthority(unittest.TestCase):
    def test_valid_independent_ephemeral_roles_and_fail_closed_mutations(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        import json
        packet={"sha256":"a"*64}
        roots={}
        attest=[]
        for index,role in enumerate(ROLES):
            private=Ed25519PrivateKey.generate()
            roots[role]={
                "key_id":"fixture-key-%d"%index,
                "approver_id":"fixture-approver-%d"%index,
                "public_key_hex":private.public_key().public_bytes(
                    Encoding.Raw,PublicFormat.Raw).hex(),
                "enabled":True}
            body={"schema":SCHEMA,"role":role,
                  "key_id":roots[role]["key_id"],
                  "approver_id":roots[role]["approver_id"],
                  "subject_sha256":packet["sha256"],
                  "issued_at_utc":"2026-11-01T00:00:00Z",
                  "expires_at_utc":"2026-12-01T00:00:00Z"}
            signature=private.sign(json.dumps(
                body,sort_keys=True,separators=(",",":"),
                ensure_ascii=True,allow_nan=False).encode("ascii")).hex()
            attest.append({**body,"signature_hex":signature})
        result=verify_role_attestations(
            packet,attest,roots,"2026-11-07T00:00:00Z")
        self.assertEqual(set(result["roles"]),set(ROLES))
        self.assertEqual(result["trading_authority"],"NONE")
        cases=[
            ("missing-role",attest[:-1],roots,"2026-11-07T00:00:00Z"),
            ("expired",attest,roots,"2026-12-07T00:00:00Z"),
            ("signature-tamper",[
                {**a,"signature_hex":"f"*128} if i==0 else a
                for i,a in enumerate(attest)],roots,"2026-11-07T00:00:00Z"),
            ("changed-subject",[
                {**a,"subject_sha256":"b"*64} if i==0 else a
                for i,a in enumerate(attest)],roots,"2026-11-07T00:00:00Z"),
            ("disabled-key",attest,{
                **roots,ROLES[0]:{**roots[ROLES[0]],"enabled":False}
            },"2026-11-07T00:00:00Z"),
        ]
        for label,docs,registry,now in cases:
            with self.subTest(label=label):
                with self.assertRaises(ResultsStoreError):
                    verify_role_attestations(packet,docs,registry,now)
    def test_insecure_runtime_default_stays_blocked(self):
        with self.assertRaises(ResultsStoreError):
            verify_role_attestations({"sha256":"a"*64},None,None,None)
if __name__=="__main__":
    unittest.main()
