"""Provider-neutral vintage admission. Callers supply independent custody pins."""
from .contracts import canonical, digest, timestamp
from .discoverer_view import seal, verify
from .source_view import require, is_pin, validate_record


def admit_vintage(registry, registry_pin, observation, observation_pin, rights, rights_pin, *, access_ms):
    verify(registry,registry_pin)
    timestamp(access_ms)
    require(registry["schema"]=="aql.core.source-registry.v1" and registry["authority"]=="NONE"
            and len(canonical(registry))<=64_000 and len(registry["sources"])<=64,"REGISTRY_SCOPE")
    require(is_pin(observation_pin) and digest(observation)==observation_pin and len(canonical(observation))<=16_000,
            "VINTAGE_PIN")
    require(is_pin(rights_pin) and digest(rights)==rights_pin and observation["rights"]==rights_pin,
            "RIGHTS_PIN")
    source = registry["sources"].get(observation["source"])
    if source is None or source["status"]!="ADMITTED":
        return seal(dict(status="UNKNOWN",reason="BLOCKED_SOURCE",record=None))
    require(source["market"]==observation["market"] and source["mode"]==observation["grade"]
            and is_pin(source["terms_sha256"]) and source["region"]
            and source["rights_sha256"]==rights_pin and source["use"]=="MONITOR_ONLY",
            "SOURCE_ADMISSION_BINDING")
    validate_record(observation,rights,source=observation["source"],market=source["market"],use="MONITOR_ONLY")
    if rights["state"]!="VERIFIED" or "MONITOR_ONLY" not in rights["uses"]:
        return seal(dict(status="UNKNOWN",reason="RIGHTS_UNAVAILABLE",record=None))
    if not rights["valid_from"]<=access_ms<min(rights["expires_at"],timestamp(source["retention_until_ms"])):
        return seal(dict(status="UNKNOWN",reason="RIGHTS_OR_RETENTION_EXPIRED",record=None))
    clocks = [observation[k] for k in ("event_at","published_at","received_at","committed_at")]
    if (not observation["final"] or any(x is None for x in clocks) or clocks!=sorted(clocks)
            or clocks[-1]>access_ms):
        return seal(dict(status="UNKNOWN",reason="VINTAGE_NOT_FINAL_OR_CLOCK_UNKNOWN",record=None))
    if observation["grade"]=="PIT_ATTESTED" and observation["known_at"]>access_ms:
        return seal(dict(status="UNKNOWN",reason="FUTURE_KNOWN_AT",record=None))
    return seal(dict(status="ADMITTED",reason=None,record=observation,record_sha256=observation_pin,
                     registry_sha256=registry_pin,authority="NONE"))
