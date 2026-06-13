"""SQLite store for DNS-resolver log records.

Schema is intentionally narrow: indexed columns for the fields we expect to
filter on (timestamp, src, query_name, action, category), with the full
record kept as JSON in `raw` for ad-hoc DuckDB / json_extract queries.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS dns_logs (
    id          INTEGER PRIMARY KEY,
    ingested_at REAL    NOT NULL,
    log_time    TEXT,
    src_ip      TEXT,
    query_name  TEXT,
    query_type  TEXT,
    action      TEXT,
    category    TEXT,
    raw         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS dns_logs_log_time   ON dns_logs(log_time);
CREATE INDEX IF NOT EXISTS dns_logs_src_ip     ON dns_logs(src_ip);
CREATE INDEX IF NOT EXISTS dns_logs_query_name ON dns_logs(query_name);
CREATE INDEX IF NOT EXISTS dns_logs_action     ON dns_logs(action);
"""

# SLS field names vary across log-types (dns-security, threat, etc.); pick
# the first non-null we see and stuff the rest into raw.
_TIME_KEYS  = ("receive_time", "time_generated", "log_time", "@timestamp")
_SRC_KEYS   = ("src", "src_ip", "source_ip", "client_ip")
_QNAME_KEYS = ("query_name", "name", "domain", "url")
_QTYPE_KEYS = ("query_type", "type", "dns_type")
_ACT_KEYS   = ("action", "verdict", "category_action")
_CAT_KEYS   = ("category_of_app", "category", "subtype")


def _pick(rec, keys):
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return str(v)
    return None


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM dns_logs").fetchone()[0]

    def insert_many(self, records: list[dict]):
        now = time.time()
        rows = []
        for r in records:
            if not isinstance(r, dict):
                continue
            rows.append((
                now,
                _pick(r, _TIME_KEYS),
                _pick(r, _SRC_KEYS),
                _pick(r, _QNAME_KEYS),
                _pick(r, _QTYPE_KEYS),
                _pick(r, _ACT_KEYS),
                _pick(r, _CAT_KEYS),
                json.dumps(r, separators=(",", ":")),
            ))
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO dns_logs(ingested_at, log_time, src_ip, query_name, "
                "query_type, action, category, raw) VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
            self._conn.commit()
