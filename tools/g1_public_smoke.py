"""One-shot public market-data checks: no credentials, orders or persistence."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error
import websocket


def main():
    result = {"scope": "public BTCUSDT 1m; no database, account or order calls",
              "host_utc": datetime.now(timezone.utc).isoformat()}
    start = time.monotonic()
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=100"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = resp.read(1_000_001)
            if len(payload) > 1_000_000:
                raise ValueError("Oversized response")
            rows = json.loads(payload)
            if not isinstance(rows, list) or len(rows) > 100 or not rows:
                raise ValueError("Unexpected kline response")
            now_ms = int(time.time()*1000)
            opens = [int(r[0]) for r in rows]
            result["rest"] = {
                "status":"PASS", "http_status":resp.status,
                "server_date":resp.headers.get("Date"),
                "latency_ms":round((time.monotonic()-start)*1000,2),
                "rows":len(rows), "first_open_ms":opens[0],"last_open_ms":opens[-1],
                "closed_rows":sum(int(r[6]) < now_ms for r in rows),
                "unique_opens":len(set(opens)),
                "ordered_contiguous":all(b-a==60000 for a,b in zip(opens,opens[1:])),
                "used_weight":resp.headers.get("X-MBX-USED-WEIGHT-1M")}
    except Exception as exc:
        result["rest"]={"status":"BLOCKED","error_type":type(exc).__name__,
                        "http_status":getattr(exc,"code",None),
                        "latency_ms":round((time.monotonic()-start)*1000,2),
                        "attempts":1}
    if result["rest"].get("status") == "PASS":
        from email.utils import parsedate_to_datetime
        date = result["rest"].get("server_date")
        skew = ((parsedate_to_datetime(date).timestamp()-datetime.fromisoformat(
            result["host_utc"]).timestamp()) if date else None)
        result["rest"]["server_minus_host_seconds"] = skew
        result["rest"]["transport_status"] = "PASS"
        result["rest"]["temporal_status"] = ("BLOCKED_CLOCK_SKEW" if skew is None or abs(skew)>5 else "OBSERVED_ONLY")
        result["rest"]["status"] = "PASS_TRANSPORT_ONLY"
    sock=None
    start=time.monotonic()
    try:
        sock=websocket.create_connection("wss://stream.binance.com:9443/ws/btcusdt@kline_1m",
                                         timeout=5)
        observations=[]
        deadline=time.monotonic()+10
        while len(observations)<3 and time.monotonic()<deadline:
            sock.settimeout(min(3,max(.1,deadline-time.monotonic())))
            data=json.loads(sock.recv())
            k=data["k"]
            if k["s"]!="BTCUSDT" or k["i"]!="1m":
                raise ValueError("Unexpected stream identity")
            observations.append({"event_ms":data["E"],"bar_open_ms":k["t"],
                                 "bar_close_ms":k["T"],"final":k["x"],
                                 "received_utc":datetime.now(timezone.utc).isoformat()})
        result["websocket"]={"status":"PASS" if observations else "BLOCKED",
                             "elapsed_ms":round((time.monotonic()-start)*1000,2),
                             "observations":observations,
                             "limitation":"Receipt only; no closed-bar/reconnect proof"}
    except Exception as exc:
        result["websocket"]={"status":"BLOCKED","error_type":type(exc).__name__,
                            "elapsed_ms":round((time.monotonic()-start)*1000,2),
                            "attempts":1}
    finally:
        if sock is not None:
            sock.close()
    if result["websocket"].get("status") == "PASS":
        observations = result["websocket"]["observations"]
        skewed = any(abs(o["event_ms"]/1000-datetime.fromisoformat(
            o["received_utc"]).timestamp())>5 for o in observations)
        result["websocket"]["transport_status"] = "PASS"
        result["websocket"]["temporal_status"] = ("BLOCKED_CLOCK_SKEW" if skewed else "OBSERVED_ONLY")
        result["websocket"]["status"] = "PASS_TRANSPORT_ONLY"
    path=Path("evidence/g1_completion_public_smoke.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
