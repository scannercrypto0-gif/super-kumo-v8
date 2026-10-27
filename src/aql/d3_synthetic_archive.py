"""Opt-in D3 offline synthetic sparse catalog verification.

No network, trading, pipeline hooks, backup custody or filesystem writes.
A caller MUST retain the expected digest independently of the catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

VERSION = "AQL-D3-SYNTHETIC-V1"
STATES = frozenset({"CONFIRMED", "WITHHELD", "IN_DOUBT", "UNKNOWN"})


class D3IntegrityError(ValueError):
    """Fail-closed catalog/receipt verification error."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class SparseRecord:
    sequence: int
    state: str
    source_digest: str
    target_receipt_digest: str | None = None


def _records(rows: tuple[SparseRecord, ...]) -> list[dict[str, object]]:
    return [{"sequence": r.sequence, "state": r.state,
             "source_digest": r.source_digest,
             "target_receipt_digest": r.target_receipt_digest} for r in rows]


def _validate(rows: tuple[SparseRecord, ...]) -> None:
    seen: set[int] = set()
    for row in rows:
        if type(row.sequence) is not int or row.sequence < 0 or row.sequence in seen:
            raise D3IntegrityError("invalid or duplicate sequence")
        seen.add(row.sequence)
        if row.state not in STATES:
            raise D3IntegrityError("unknown disposition")
        if len(row.source_digest) != 64 or any(c not in "0123456789abcdef" for c in row.source_digest):
            raise D3IntegrityError("invalid source digest")
        if row.state == "CONFIRMED" and not row.target_receipt_digest:
            raise D3IntegrityError("confirmed row requires independent target receipt")
        if row.state != "CONFIRMED" and row.target_receipt_digest is not None:
            raise D3IntegrityError("unconfirmed row cannot assert target receipt")
        if row.target_receipt_digest is not None and (
            len(row.target_receipt_digest) != 64
            or any(c not in "0123456789abcdef" for c in row.target_receipt_digest)
        ):
            raise D3IntegrityError("invalid receipt digest")


def build_catalog(*, generation: str, consumer: str, epoch: int,
                  rows: tuple[SparseRecord, ...]) -> dict[str, object]:
    """Create a synthetic, versioned manifest; never infer absent rows as delivered."""
    if not generation or not consumer or type(epoch) is not int or epoch < 0:
        raise D3IntegrityError("invalid catalog identity")
    _validate(rows)
    ordered = tuple(sorted(rows, key=lambda r: r.sequence))
    inventory = _records(ordered)
    payload: dict[str, object] = {
        "version": VERSION, "generation": generation, "consumer": consumer,
        "epoch": epoch, "inventory": inventory, "inventory_digest": _digest(inventory),
    }
    payload["catalog_digest"] = _digest(payload)
    return payload


def verify_catalog(catalog: Mapping[str, object], *, pinned_digest: str,
                   expected_generation: str, expected_consumer: str,
                   minimum_epoch: int, source_digests: Mapping[int, str],
                   target_receipts: Mapping[int, str]) -> tuple[SparseRecord, ...]:
    """Read-only verification against independent pinned and source/target evidence.

    A catalog's own hash is never sufficient: caller pins the digest separately.
    No implicit confirmation for gaps, withheld or in-doubt entries.
    """
    if type(minimum_epoch) is not int or minimum_epoch < 0:
        raise D3IntegrityError("invalid epoch floor")
    try:
        raw = dict(catalog)
        claimed = raw.pop("catalog_digest")
        if set(raw) != {"version", "generation", "consumer", "epoch", "inventory", "inventory_digest"}:
            raise D3IntegrityError("unexpected manifest schema")
        if raw["version"] != VERSION or raw["generation"] != expected_generation or raw["consumer"] != expected_consumer:
            raise D3IntegrityError("version or identity mismatch")
        if type(raw["epoch"]) is not int or raw["epoch"] < minimum_epoch:
            raise D3IntegrityError("stale epoch")
        if not isinstance(raw["inventory"], list) or raw["inventory_digest"] != _digest(raw["inventory"]):
            raise D3IntegrityError("inventory digest mismatch")
        if claimed != pinned_digest or claimed != _digest(raw):
            raise D3IntegrityError("catalog digest mismatch")
        rows = tuple(SparseRecord(**item) for item in raw["inventory"])
        _validate(rows)
        if list(raw["inventory"]) != _records(tuple(sorted(rows, key=lambda r: r.sequence))):
            raise D3IntegrityError("noncanonical inventory")
        if set(source_digests) != {r.sequence for r in rows}:
            raise D3IntegrityError("source inventory coverage mismatch")
        for row in rows:
            if source_digests[row.sequence] != row.source_digest:
                raise D3IntegrityError("source evidence mismatch")
            if row.state == "CONFIRMED":
                if target_receipts.get(row.sequence) != row.target_receipt_digest:
                    raise D3IntegrityError("target evidence missing or changed")
            elif row.sequence in target_receipts:
                raise D3IntegrityError("unexpected receipt for unconfirmed row")
        return rows
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        if isinstance(exc, D3IntegrityError):
            raise
        raise D3IntegrityError("malformed catalog") from exc
