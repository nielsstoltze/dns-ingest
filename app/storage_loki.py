"""Push SLS records into Loki via /loki/api/v1/push.

Each record becomes one stream-line stamped with ns-precision. Labels are
kept small (job=dns-ingest, src=<ip-or-unknown>) so we don't blow up
Loki's cardinality budget — the rich fields live in the line as JSON.
"""
import json
import time
import urllib.request


class LokiPusher:
    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def push_many(self, records: list[dict]):
        if not records:
            return
        # Group by src to bound the number of streams
        streams: dict[str, list[tuple[str, str]]] = {}
        now_ns = int(time.time() * 1e9)
        for i, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            src = str(r.get("src") or r.get("src_ip") or "unknown")
            ts = str(now_ns + i)
            line = json.dumps(r, separators=(",", ":"))
            streams.setdefault(src, []).append((ts, line))

        payload = {
            "streams": [
                {"stream": {"job": "dns-ingest", "src": src}, "values": vs}
                for src, vs in streams.items()
            ]
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.url}/loki/api/v1/push", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=self.timeout).read()
