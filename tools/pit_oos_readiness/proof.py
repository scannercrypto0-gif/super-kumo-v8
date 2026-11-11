"""Offline verifier for future signed evidence using separately retained public pins."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from research_wp_r0.frozen_research_plan import verify_research_plan
from research_wp_r0.strategy_definition import canonical

ROLES = ("owner", "witness", "publisher", "receiver", "custodian")


def need(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return sha256(raw).hexdigest()


def is_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def openssl_path():
    executable = shutil.which("openssl")
    if executable:
        return executable
    for parent in (Path("C:/Program Files/Git"), Path("C:/Program Files (x86)/Git")):
        candidate = parent / "usr/bin/openssl.exe"
        if candidate.is_file():
            return str(candidate)
    raise ValueError("OPENSSL_REQUIRED")


def public_key_identity(pem):
    need(isinstance(pem, str) and len(pem) <= 256, "PUBLIC_KEY_FORMAT")
    lines = pem.strip().splitlines()
    need(len(lines) == 3 and lines[0] == "-----BEGIN PUBLIC KEY-----"
         and lines[2] == "-----END PUBLIC KEY-----", "PUBLIC_KEY_FORMAT")
    der = base64.b64decode(lines[1], validate=True)
    need(len(der) == 44 and der.startswith(bytes.fromhex("302a300506032b6570032100")), "ED25519_KEY_REQUIRED")
    return der


def verify_signature(role, receipt, key):
    need(set(receipt) == {"role", "payload", "signature"} and receipt["role"] == role, "RECEIPT_ROLE")
    signature = base64.b64decode(receipt["signature"], validate=True)
    need(len(signature) == 64, "ED25519_SIGNATURE_SIZE")
    with tempfile.TemporaryDirectory(prefix="atlas-public-proof-") as folder:
        root = Path(folder)
        (root / "key.pem").write_text(key, encoding="ascii")
        (root / "message").write_bytes(canonical({"role": role, "payload": receipt["payload"]}))
        (root / "signature").write_bytes(signature)
        result = subprocess.run([openssl_path(), "pkeyutl", "-verify", "-pubin", "-rawin",
                                 "-inkey", str(root / "key.pem"), "-in", str(root / "message"),
                                 "-sigfile", str(root / "signature")],
                                capture_output=True, timeout=10, check=False)
        need(result.returncode == 0, f"SIGNATURE_INVALID_{role.upper()}")
    return receipt["payload"]


def verify_bundle(bundle, trust, expected_trust_sha, plan_raw):
    """Return integrity/chronology relative to caller pins, never PIT or OOS acceptance."""
    need(sha(canonical(trust)) == expected_trust_sha, "EXTERNAL_TRUST_PIN")
    need(set(trust) == set(ROLES) == set(bundle), "PROOF_POPULATION")
    need(len({public_key_identity(key) for key in trust.values()}) == len(ROLES), "INDEPENDENT_ROLE_KEYS")
    owner, witness, release, received, custody = (
        verify_signature(role, bundle[role], trust[role]) for role in ROLES)
    owner_fields = {"decision", "authority", "plan_sha256", "source_sha256", "rights_sha256",
                    "terms_version", "rights_use", "terms_from_ms", "terms_until_ms",
                    "approval_ms", "first_open_ms", "train_end_ms", "validation_start_ms",
                    "validation_end_ms", "oos_start_ms", "oos_end_ms", "step_ms",
                    "custody_sha256", "slot_limit", "byte_limit", "spend_ceiling"}
    need(set(owner) == owner_fields and owner["decision"] == "APPROVED_RESEARCH_ONLY"
         and owner["authority"] == "NONE" and owner["rights_use"] == "PERSONAL_NONCOMMERCIAL_RESEARCH"
         and isinstance(owner["terms_version"], str) and bool(owner["terms_version"]), "OWNER_SCOPE")
    plan = verify_research_plan(plan_raw, owner["plan_sha256"])
    need(owner["source_sha256"] == plan["dataset_digest"] and all(
        is_sha(owner[k]) for k in ("source_sha256", "rights_sha256", "custody_sha256")), "OWNER_PINS")
    times = {k: owner[k] for k in ("first_open_ms", "train_end_ms", "validation_start_ms",
                                   "validation_end_ms", "oos_start_ms", "oos_end_ms", "step_ms")}
    need(sha(canonical(times)) == plan["split_digest"], "SPLIT_BINDING")
    need(owner["step_ms"] == 900_000 and all(type(v) is int and 0 <= v <= 2**53-1 for v in times.values())
         and all(v % owner["step_ms"] == 0 for v in times.values())
         and owner["first_open_ms"] < owner["train_end_ms"]
         and owner["train_end_ms"] + 259_200_000 <= owner["validation_start_ms"] < owner["validation_end_ms"]
         and owner["validation_end_ms"] + 259_200_000 <= owner["oos_start_ms"] < owner["oos_end_ms"],
         "SPLIT_GRID_OR_EMBARGO")
    slots = sum((end - start) // owner["step_ms"] for start, end in (
        (owner["first_open_ms"], owner["train_end_ms"]),
        (owner["validation_start_ms"], owner["validation_end_ms"]),
        (owner["oos_start_ms"], owner["oos_end_ms"])))
    need(all(type(owner[k]) is int for k in ("slot_limit", "byte_limit", "spend_ceiling"))
         and slots <= owner["slot_limit"] <= 4096 and 0 < owner["byte_limit"] <= 16_000_000
         and owner["spend_ceiling"] == 0, "OWNER_BUDGET")
    need(set(witness) == {"owner_sha256", "plan_sha256", "witnessed_ms"}
         and witness["owner_sha256"] == sha(canonical(bundle["owner"]))
         and witness["plan_sha256"] == owner["plan_sha256"], "WITNESS_BINDING")
    need(set(release) == {"source_sha256", "rights_sha256", "open_ms", "close_ms",
                          "first_available_ms", "version", "correction_of", "content_sha256"}
         and release["source_sha256"] == owner["source_sha256"]
         and release["rights_sha256"] == owner["rights_sha256"] and is_sha(release["content_sha256"]),
         "PUBLISHER_BINDING")
    need(type(release["version"]) is int and release["version"] == 1 and release["correction_of"] is None,
         "CORRECTION_QUARANTINE")
    need(set(received) == {"release_sha256", "received_ms"}
         and received["release_sha256"] == sha(canonical(bundle["publisher"])), "RECEIVER_BINDING")
    need(set(custody) == {"received_sha256", "content_sha256", "custody_sha256",
                           "committed_ms", "immutable_ack", "holdout"}
         and custody["received_sha256"] == sha(canonical(bundle["receiver"]))
         and custody["content_sha256"] == release["content_sha256"]
         and custody["custody_sha256"] == owner["custody_sha256"]
         and custody["immutable_ack"] is True and custody["holdout"] == "SEALED_UNOPENED",
         "CUSTODY_ACK_BINDING")
    ordered = (owner["terms_from_ms"], owner["approval_ms"], witness["witnessed_ms"],
               release["open_ms"], release["close_ms"], release["first_available_ms"],
               received["received_ms"], custody["committed_ms"], owner["terms_until_ms"])
    need(all(type(v) is int and 0 <= v <= 2**53-1 for v in ordered)
         and ordered == tuple(sorted(ordered))
         and owner["approval_ms"] <= witness["witnessed_ms"] < owner["first_open_ms"]
         and release["open_ms"] == owner["first_open_ms"]
         and release["close_ms"] == release["open_ms"] + owner["step_ms"] - 1
         and release["close_ms"] < release["first_available_ms"]
         and custody["committed_ms"] < owner["terms_until_ms"]
         and owner["oos_end_ms"] <= owner["terms_until_ms"], "PROSPECTIVE_CHRONOLOGY")
    return dict(status="SIGNED_PROOF_CONTRACT_VERIFIED_RELATIVE_TO_SUPPLIED_PINS",
                bundle_sha256=sha(canonical(bundle)), plan_sha256=owner["plan_sha256"],
                trust_sha256=expected_trust_sha, collection="NOT_ACTIVATED",
                real_science="REAL_PIT_OOS_BLOCKED", holdout="SEALED_UNOPENED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("trust", type=Path)
    parser.add_argument("trust_sha256")
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    from research_wp_r0.strategy_definition import load_json
    def bounded(path):
        need(path.is_file() and path.stat().st_size <= 100_000, "BOUNDED_INPUT")
        return path.read_bytes()
    result = verify_bundle(load_json(bounded(args.bundle).decode()), load_json(bounded(args.trust).decode()),
                           args.trust_sha256, bounded(args.plan))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
