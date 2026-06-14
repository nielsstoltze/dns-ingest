"""Send a fake SLS Stacked-JSON (NDJSON) batch to the local receiver."""
import gzip
import json
import sys
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8093/v1/ingest"

records = [
    {"receive_time": "2026-06-13 12:00:00", "src": "10.0.0.50",
     "query_name": "stacked.test", "action": "allow"},
    {"receive_time": "2026-06-13 12:00:01", "src": "10.0.0.50",
     "query_name": "stacked2.test", "action": "allow"},
]
# NDJSON: one JSON object per line, no surrounding array
body = gzip.compress(("\n".join(json.dumps(r) for r in records) + "\n").encode())

req = urllib.request.Request(URL, data=body, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Content-Encoding", "gzip")
r = urllib.request.urlopen(req, timeout=10)
print(f"HTTP {r.status}")
