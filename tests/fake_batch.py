"""Send a fake SLS-style batch to the local receiver."""
import gzip
import json
import sys
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8093/v1/ingest"

records = [
    {
        "receive_time": "2026-06-13 11:00:00",
        "src": "10.0.0.42",
        "query_name": "example.com",
        "query_type": "A",
        "action": "allow",
        "category_of_app": "computer-and-internet-info",
        "log_source": "fake",
    },
    {
        "receive_time": "2026-06-13 11:00:01",
        "src": "10.0.0.42",
        "query_name": "malware.test",
        "query_type": "A",
        "action": "sinkhole",
        "category_of_app": "malware",
        "log_source": "fake",
    },
]

body = gzip.compress(json.dumps(records).encode())
req = urllib.request.Request(URL, data=body, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Content-Encoding", "gzip")
r = urllib.request.urlopen(req, timeout=10)
print(f"HTTP {r.status}")
