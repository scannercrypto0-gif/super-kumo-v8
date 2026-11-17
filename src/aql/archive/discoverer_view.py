"""Bounded read-only Core projections for the pinned Discoverer seam."""
from copy import deepcopy

from .contracts import canonical, digest, timestamp
from .source_view import as_of_view, is_pin, require

SCHEMA = "aql.core.discoverer-inventory.v1"
FEATURES = frozenset(("price","volume","liquidity","btc","sector","paxg","news","macro","monitor"))
MAX_BYTES = 256_000


def seal(body):
    return {**body,"sha256":digest(body)}


def verify(doc, pin):
    require(is_pin(pin) and doc["sha256"] == pin == digest({k:v for k,v in doc.items() if k!="sha256"}),"MANIFEST_PIN")


class DiscovererView:
    """The owner supplies bytes and their independent pin from Core custody."""

    def __init__(self, inventory, expected, *, access_ms):
        timestamp(access_ms)
        require(len(canonical(inventory)) <= MAX_BYTES,"INVENTORY_BOUND")
        verify(inventory,expected)
        require(set(inventory) == {"schema","mode","venue","market","members","membership_effective",
                                   "membership_expires","series","sha256"}
                and inventory["schema"] == SCHEMA and inventory["mode"] in ("TEST_ONLY","SOURCE_EVIDENCE")
                and len(inventory["members"]) <= 32 and len(inventory["series"]) <= 128,
                "INVENTORY_SCHEMA")
        require(timestamp(inventory["membership_effective"]) < timestamp(inventory["membership_expires"]),
                "MEMBERSHIP_WINDOW")
        self.inventory = deepcopy(inventory)
        self.access_ms = access_ms
        self.index = {}
        for item in self.inventory["series"]:
            require(set(item) == {"symbol","feature","source","market","status","retention_until_ms",
                                  "definition","records","pins","rights"},"SERIES_SCHEMA")
            key = item["symbol"],item["feature"]
            require(key not in self.index and key[0] in inventory["members"] and key[1] in FEATURES|{"outcome"},
                    "SERIES_IDENTITY")
            require(item["status"] in ("ADMITTED","BLOCKED_SOURCE") and len(item["records"]) <= 32,
                    "SERIES_ADMISSION")
            timestamp(item["retention_until_ms"])
            definition = item["definition"]
            require(set(definition) == {"id","version","unit","scale","operation"}
                    and type(definition["scale"]) is int and definition["scale"] > 0
                    and definition["operation"] == "SIGNED_INTEGER_AT_DECLARED_SCALE",
                    "FEATURE_DEFINITION")
            self.index[key] = item

    def _membership(self, at):
        require(self.inventory["membership_effective"] <= at < self.inventory["membership_expires"],
                "STALE_OR_MISSING_MEMBERSHIP")

    def _slot(self, symbol, feature, key, cutoff, max_age, *, min_event=0, histories=False):
        item = self.index.get((symbol,feature))
        if item is None or item["status"] != "ADMITTED":
            return [],"BLOCKED_SOURCE",None
        if self.access_ms >= item["retention_until_ms"]:
            return [],"RETENTION_EXPIRED",None
        records = [r for r in item["records"] if r["key"] == key]
        pins = {(key,int(version)):pin for version,pin in item["pins"].get(key,{}).items()}
        args = dict(expected_keys=[key],rights_by_digest=item["rights"],source=item["source"],
                    market=item["market"],cutoff=cutoff,max_age_ms=max_age,use="MONITOR_ONLY",
                    require_pit=self.inventory["mode"]=="SOURCE_EVIDENCE")
        view = as_of_view(records,pins=pins,**args)
        slot = view["slots"][0]
        if slot["reason"]:
            return [],slot["reason"],view["digest"]
        chosen = slot["record"]
        if chosen["event_at"] is None or chosen["published_at"] is None:
            return [],"CLOCK_UNKNOWN",view["digest"]
        if not min_event <= chosen["event_at"] <= chosen["published_at"]:
            return [],"EVENT_OUTSIDE_WINDOW",view["digest"]
        # Source grade never crosses modes. Current retention and legal use
        # remain required even for a historical query.
        grade = "TEST_ONLY" if self.inventory["mode"]=="TEST_ONLY" else "PIT_ATTESTED"
        require(chosen["grade"] == grade,"EVIDENCE_MODE")
        right = item["rights"][chosen["rights"]]
        if not right["valid_from"] <= self.access_ms < right["expires_at"]:
            return [],"CURRENT_RIGHTS_EXPIRED",view["digest"]
        selected = [chosen]
        if histories and chosen["version"] > 1:
            selected = []
            for version in range(1,chosen["version"]+1):
                subset = [r for r in records if r["version"]<=version]
                prefix = as_of_view(subset,pins={k:v for k,v in pins.items() if k[1]<=version},**args)["slots"][0]
                original = prefix["record"]
                if original is None or original["version"] != version or original["grade"] != grade:
                    return [],"REVISION_PARENT_UNAVAILABLE",view["digest"]
                if original["event_at"] is None or original["published_at"] is None or not (
                    min_event <= original["event_at"] <= original["published_at"]
                ):
                    return [],"REVISION_PARENT_UNAVAILABLE",view["digest"]
                rights = item["rights"][original["rights"]]
                if not rights["valid_from"] <= self.access_ms < rights["expires_at"]:
                    return [],"CURRENT_RIGHTS_EXPIRED",view["digest"]
                selected.append(original)
        return selected,None,view["digest"]

    def snapshot(self, slot, plan, plan_pin):
        """Project fixture outcomes. Production must use a separately adopted schema."""
        require(self.inventory["mode"]=="TEST_ONLY","DISCOVERER_FIXTURE_CONSUMER_ONLY")
        timestamp(slot)
        require(slot <= self.access_ms,"FUTURE_ASOF")
        verify(plan,plan_pin)
        self._membership(slot)
        require(plan["members"] == self.inventory["members"] and
                (plan["venue"],plan["market"]) == (self.inventory["venue"],self.inventory["market"]),
                "MEMBERSHIP_OR_MARKET_BINDING")
        rows, unavailable = {},{}
        for symbol in sorted(plan["members"]):
            records,reason,_ = self._slot(symbol,"outcome",f"outcome:{slot}",slot,plan["step"])
            if reason:
                unavailable[symbol] = reason
                continue
            record = records[0]
            value = record["value"]
            require(set(value) == {"return_bps","onset","end"} and type(value["return_bps"]) is int
                    and value["onset"] == slot-plan["step"]
                    and value["onset"] < value["end"] == record["event_at"] <= record["published_at"],
                    "OUTCOME_BINDING")
            if slot-value["end"] > plan["max_outcome_lag_ms"]:
                unavailable[symbol] = "STALE_OUTCOME"
                continue
            rows[symbol] = dict(**value,published=record["published_at"],received=record["received_at"],
                                known_at=record["committed_at"],receipt_sha256=digest(record))
        fixture = seal(dict(schema="aql.core.discoverer-snapshot.fixture.v1",slot=slot,
                            venue=self.inventory["venue"],market=self.inventory["market"],
                            source_class="TEST_ONLY",authority="NONE",
                            membership_sha256=digest(plan["members"]),observations=rows))
        evidence = seal(dict(inventory_sha256=self.inventory["sha256"],fixture_sha256=fixture["sha256"],
                             availability_basis="SYNTHETIC_COMMIT_CLOCK_ONLY",unavailable=unavailable))
        return fixture,evidence

    def context(self, request, expected):
        verify(request,expected)
        cutoff = timestamp(request["cutoff_exclusive_ms"])
        require(cutoff <= self.access_ms,"FUTURE_ASOF")
        start = timestamp(request["start_ms"])
        require(request["schema"]=="aql.core.discoverer-context-query.v1"
                and request["venue"]==self.inventory["venue"] and request["market"]==self.inventory["market"]
                and request["symbol"] in self.inventory["members"] and is_pin(request["outcome_identity_sha256"])
                and start < cutoff and request["authority"]=="NONE" and request["scanner_mode"]=="MONITOR_ONLY"
                and type(request["max_records"]) is int and 1 <= request["max_records"] <= 32
                and set(request["features"]) <= FEATURES and len(set(request["features"])) == len(request["features"]),
                "CONTEXT_REQUEST_SCOPE")
        self._membership(cutoff)
        rows, detail, unavailable = [],[],{}
        for feature in sorted(request["features"]):
            symbol = request["symbol"]
            records,reason,parent = self._slot(symbol,feature,f"context:{cutoff}",cutoff-1,cutoff-start,
                                               min_event=start,histories=True)
            if reason:
                unavailable[feature] = reason
                continue
            if len(detail)+len(records) > request["max_records"]:
                unavailable[feature] = "RESPONSE_BUDGET"
                continue
            for record in records:
                require(type(record["value"]) is int and abs(record["value"]) <= 1_000_000,"FEATURE_INTEGER")
                detail.append(dict(feature=feature,definition=self.index[(symbol,feature)]["definition"],
                                   original=record,record_sha256=digest(record),view_sha256=parent,
                                   rights_receipt=self.index[(symbol,feature)]["rights"][record["rights"]],
                                   retention_until_ms=self.index[(symbol,feature)]["retention_until_ms"]))
                if self.inventory["mode"] == "TEST_ONLY":
                    rows.append(dict(feature=feature,value=record["value"],effective=record["event_at"],
                                     published=record["published_at"],received=record["received_at"],
                                     known_at=record["committed_at"],version=record["version"],
                                     source_sha256=digest(record),parent_sha256=record["prior"],mode="MONITOR_ONLY"))
        evidence = seal(dict(schema="aql.core.discoverer-context-evidence.v1",request_sha256=expected,
                             request=deepcopy(request),
                             inventory_sha256=self.inventory["sha256"],source_class=self.inventory["mode"],
                             cutoff_exclusive_ms=cutoff,records=detail,unavailable=unavailable,
                             authority="NONE",coverage="COMPLETE" if not unavailable else "PARTIAL" if detail else "UNKNOWN"))
        fixture = None
        if self.inventory["mode"] == "TEST_ONLY":
            fixture = seal(dict(schema="aql.core.discoverer-context.fixture.v1",query_sha256=expected,
                                source_class="TEST_ONLY",records=rows))
        return fixture,evidence


def factory_inputs(candidate, candidate_pin, evidence, evidence_pin):
    """Pass a typed predicate and admitted vintages to Factory, without evaluation."""
    verify(candidate,candidate_pin)
    verify(evidence,evidence_pin)
    require(candidate["schema"]=="aql.discoverer.precursor-proposal.v1" and candidate["authority"]=="NONE"
            and candidate["holdout"]=="SEALED_UNOPENED" and evidence["authority"]=="NONE"
            and evidence["schema"]=="aql.core.discoverer-context-evidence.v1","FACTORY_INPUT_SCOPE")
    rule = candidate["comparison"]
    require(rule["feature"] in FEATURES and type(rule["trigger"]) is int
            and rule["direction"] in ("UP","DOWN"),"FACTORY_PREDICATE")
    values = [row for row in evidence["records"] if row["feature"]==rule["feature"]]
    require(len({digest(row["definition"]) for row in values}) <= 1,"FEATURE_DEFINITION_DRIFT")
    return seal(dict(schema="aql.core.factory-precursor-input.v1",candidate_sha256=candidate_pin,
                     context_sha256=evidence_pin,source_class=evidence["source_class"],
                     inventory_sha256=evidence["inventory_sha256"],request_sha256=evidence["request_sha256"],
                     candidate_policy_sha256=candidate["policy_sha256"],
                     exclusive_cutoff_ms=evidence["cutoff_exclusive_ms"],subject=evidence["request"]["symbol"],
                     rule=dict(feature=rule["feature"],operator="GE",threshold=rule["trigger"],
                               outcome_direction=rule["direction"]),
                     feature_vintages=values,availability="ADMITTED" if values else "UNKNOWN",
                     evaluation="FACTORY_OWNED_NOT_RUN",holdout="SEALED_UNOPENED",authority="NONE"))
