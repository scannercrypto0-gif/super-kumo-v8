"""Client for an operator-installed renewable shared-egress authority."""
from tools.atlas_single_receipt import need


class Lease:
    def __init__(self, authority, scope, *, now):
        self.authority = authority
        self.scope = scope
        self.now = now
        self.record = None

    def __enter__(self):
        self.record = self.authority.acquire_research_lease(**self.scope)
        try:
            self.check()
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        if isinstance(self.record, dict) and self.record.get("lease_id"):
            self.authority.release_research_lease(lease_id=self.record["lease_id"], **self.scope)

    def check(self):
        record = self.record
        now = self.now()
        self.validate(record, now)
        if record["expires_ms"] - now <= 35_000:
            renewed = self.authority.renew_research_lease(lease_id=record["lease_id"], **self.scope)
            self.validate(renewed, self.now())
            need(renewed["lease_id"] == record["lease_id"] and
                 renewed["expires_ms"] > record["expires_ms"], "LEASE_RENEWAL_INVALID")
            self.record = renewed
        return (self.record["expires_ms"] - self.now()) / 1000

    def validate(self, record, now):
        need(isinstance(record, dict) and bool(record.get("lease_id")) and
             record.get("scope") == self.scope, "LEASE_SCOPE_INVALID")
        expires = record.get("expires_ms")
        need(type(expires) is int and now < expires <= now + 120_000, "LEASE_EXPIRED_OR_INVALID")
        used, limit = record.get("reserved_and_used"), record.get("limit")
        need(type(used) is int and type(limit) is int and
             self.scope["connections"] <= used <= limit // 2, "LEASE_HEADROOM_UNVERIFIED")
