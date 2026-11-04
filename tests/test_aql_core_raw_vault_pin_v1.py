"""Core #253 — exact pinned PR #211 actual RawVault integration (Ubuntu/POSIX).

The test runner checks out the frozen #211 SHA in a *separate* directory.
It exercises the public RawVault API without modifying #211 or importing it
into our protected Core code unless the owner explicitly supplies the vault.
Synthetic original ZIP only, never private price data.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import raw_sha
from research_wp_r0.aql_core_backbone_local_v1 import (
    admit_local_original, query_local,
)
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.corrections import CorrectionLedger
from test_aql_archive_custody_bridge_v1 import START, WIDTH, N, spec
from test_aql_native_binance_zip_v1 import native_source


class PinnedRawVaultIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"history"
        self.vault=RawVault(Path(self.tmp.name)/"raw")
        self.source,self.member,self.checksum,self.pin=native_source()
        self.s=spec(source_label="native-monthly-zip")
        self.cutoff=START+N*WIDTH+2000

    def admit(self,source=None,checksum=None,pin=None,s=None):
        return admit_local_original(
            self.root,
            self.source if source is None else source,
            self.checksum if checksum is None else checksum,
            self.pin if pin is None else pin,
            self.s if s is None else s,
            decision_cutoff_ms=self.cutoff,vault=self.vault,
        )

    def test_actual_raw_vault_commit_readback_restart_and_source_query(self):
        first=self.admit()
        self.assertEqual(first["status"],"OFFLINE_LOCAL_WAREHOUSE_COMMITTED")
        self.assertEqual(first["vault"]["vault"],"EXISTING_PINNED_RAW_VAULT")
        self.assertEqual(first["vault"]["sha256"],raw_sha(self.source))
        self.assertEqual(self.vault.read(raw_sha(self.source)),self.source)
        self.assertEqual(len(self.vault.manifest_entries()),1)
        self.assertEqual(self.vault.recovery_scan()["status"],"CLEAN")
        self.assertEqual(self.admit(),first)
        self.assertEqual(len(self.vault.manifest_entries()),1)
        # Source SHA lives in the Vault (independent physical original bytes)
        # AND in the Core stage; SQLite owns only the derived index/receipts.
        q=query_local(
            self.root,self.s["dataset_id"],1,self.s["start_ms"],
            self.s["end_exclusive_ms"],self.cutoff,
            required_source_sha256=first["source_zip_sha256"],
        )
        self.assertEqual(q["coverage"],"COMPLETE")
        self.assertEqual(q["available_bar_count"],N)
        self.assertEqual(q["source_availability"],"RETROSPECTIVE_NON_PIT")

    def test_real_vault_append_only_corrections_and_idempotent_replay(self):
        first=self.admit()
        src,member,check,pin=native_source(change=3)
        corrected=spec(
            version=2,source_label="native-monthly-zip",
            parent_source_sha256=first["source_zip_sha256"],
            correction_reason="TEST_CORRECTED_NATIVE_ZIP",
        )
        second=self.admit(source=src,checksum=check,pin=pin,s=corrected)
        self.assertEqual(second["status"],"OFFLINE_LOCAL_WAREHOUSE_COMMITTED")
        self.assertEqual(second["vault"]["correction_ledger"],"PINNED_APPEND_ONLY")
        self.assertEqual(self.vault.read(raw_sha(src)),src)
        self.assertEqual(self.vault.read(raw_sha(self.source)),self.source)
        self.assertEqual(len(self.vault.manifest_entries()),2)
        led=CorrectionLedger(self.vault.root/"corrections.jsonl")
        chain=led.chain_for(first["vault"]["base_family_identity"])
        self.assertEqual(len(chain),1)
        self.assertEqual(chain[0].content_sha256,raw_sha(src))
        self.assertEqual(chain[0].parent_sha256,raw_sha(self.source))
        self.assertEqual(self.admit(source=src,checksum=check,pin=pin,s=corrected),
                         second)
        self.assertEqual(len(led.chain_for(first["vault"]["base_family_identity"])),1)

    def test_conflicting_corrected_generation_keeps_original_immutable(self):
        first=self.admit()
        s=spec(version=2,source_label="native-monthly-zip",
               parent_source_sha256=first["source_zip_sha256"],
               correction_reason="TEST_CORRECTION")
        changed,member,check,pin=native_source(change=2)
        self.admit(source=changed,checksum=check,pin=pin,s=s)
        new_raw,new_member,new_cs,new_pin=native_source(change=4)
        with self.assertRaises(ValueError):
            self.admit(source=new_raw,checksum=new_cs,pin=new_pin,s=s)
        self.assertEqual(self.vault.read(raw_sha(self.source)),self.source)
        self.assertEqual(self.vault.read(raw_sha(changed)),changed)
        self.assertEqual(len(self.vault.manifest_entries()),2)


if __name__=="__main__":
    unittest.main()
