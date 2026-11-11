"""Dispatch seam for fixtures. This module opens no provider connections."""
from tools.binance_live_feed.feed import INTERVALS, need, ms
from tools.binance_live_feed.quota import STREAMS


class Session:
    def __init__(self, feed, quota):
        self.feed, self.quota = feed, quota
        self.socket = None

    def connect(self, socket, now):
        need(self.socket is None, "SOCKET_ALREADY_OPEN")
        if not self.quota.connect(socket, now, sorted(STREAMS)):
            return False
        try:
            self.feed.start(now)
        except BaseException:
            self.quota.disconnect(socket, now)
            raise
        self.socket = socket
        return True

    def disconnect(self, now, *, failed=True):
        self.feed.stop(now)
        if self.socket is not None:
            self.quota.disconnect(self.socket, now, failed)
            self.socket = None

    def tick(self, now):
        if self.socket is not None and not self.quota.alive(self.socket, now):
            self.disconnect(now, failed=True)
            return False
        return self.socket is not None

    def ping(self, raw_payload, now):
        """Return the exact server ping payload for a budgeted pong."""
        need(type(raw_payload) is bytes and len(raw_payload) <= 125, "PING_PAYLOAD")
        if self.socket is not None and self.quota.ws(self.socket, now, "PONG"):
            return raw_payload
        self.disconnect(now)
        return None

    def receive(self, raw, now, commit_clock):
        need(self.tick(now), "SOCKET_UNAVAILABLE")
        try:
            return self.feed.ingest(raw, now, commit_clock)
        except Exception:
            self.disconnect(now)
            raise

    def research(self, cutoff):
        if not self.tick(cutoff):
            return self.feed.blocked("DISCONNECTED")
        return self.feed.read(cutoff)

    def recover(self, channel, row, now, commit_clock, *, server_time=None, used_weight=None):
        """Apply a mocked REST response through the same recovery budget."""
        need(channel in {*INTERVALS, "trade"} and self.socket is None, "RECOVERY_SCOPE")
        endpoint = "trades" if channel == "trade" else "klines"
        token = self.quota.rest(endpoint, now, recovery=True)
        if token is None:
            return "RECOVERY_BACKPRESSURE"
        self.quota.result(token, now, 200, used_weight=used_weight)
        if channel == "trade":
            return self.feed.recover_trade(row, now, commit_clock)
        return self.feed.recover_candle(row, channel, now, server_time, commit_clock)


def check_depth_sequence(snapshot, deltas, cutoff):
    """Sequence-only validation for deferred L2, no depth subscription or book."""
    need(0 <= cutoff-ms(snapshot["receive_ms"]) <= 2000, "STALE_DEPTH_SNAPSHOT")
    update = ms(snapshot["lastUpdateId"])
    need(len(deltas) <= 32, "DEPTH_BUFFER_BOUND")
    for delta in deltas:
        first, last = ms(delta["U"]), ms(delta["u"])
        need(first <= last and ms(delta["E"]) <= cutoff, "DEPTH_FUTURE_OR_INVALID")
        if last <= update:
            continue
        need(first <= update+1 <= last, "DEPTH_SEQUENCE_GAP")
        update = last
    return update
