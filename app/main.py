"""DNS-ingest receiver for Strata Logging Service HTTPS forwarding.

SLS forwards a gzip-encoded JSON array of log records to /v1/ingest.
We persist each record to SQLite (for SQL ad-hoc) and push to Loki
(for live tail in Grafana). Schema is intentionally permissive — SLS
flattens records to flat key/value JSON, and we keep the full payload
in a `raw` JSON column so future fields don't require a migration.
"""
import gzip
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.storage_sqlite import SQLiteStore
from app.storage_loki import LokiPusher

log = logging.getLogger("dns-ingest")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DATA_DIR = Path(os.environ.get("DNS_INGEST_DATA", "/var/lib/dns-ingest"))
DB_PATH = DATA_DIR / "dns.sqlite"
LOKI_URL = os.environ.get("LOKI_PUSH_URL", "").strip() or None
MAX_BATCH_BYTES = 8 * 1024 * 1024  # 8 MiB after decompress, SLS docs say ~2.25 MiB

state = {"sqlite": None, "loki": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["sqlite"] = SQLiteStore(DB_PATH)
    state["loki"] = LokiPusher(LOKI_URL) if LOKI_URL else None
    log.info(f"sqlite={DB_PATH}  loki={LOKI_URL or 'disabled'}")
    yield
    state["sqlite"].close()


app = FastAPI(title="dns-ingest", lifespan=lifespan)


@app.get("/health")
def health():
    s = state["sqlite"]
    return {
        "ok": True,
        "rows": s.count() if s else None,
        "loki": bool(state["loki"]),
    }


@app.post("/v1/ingest")
async def ingest(request: Request):
    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")

    enc = request.headers.get("content-encoding", "").lower()
    if "gzip" in enc:
        try:
            body = gzip.decompress(body)
        except OSError as e:
            raise HTTPException(400, f"gunzip failed: {e}")

    if len(body) > MAX_BATCH_BYTES:
        raise HTTPException(413, "batch too large")

    # SLS HTTPS forwarding offers two payload formats:
    #   Array JSON   — one big [{...}, {...}] (standard JSON)
    #   Stacked JSON — newline-delimited {...}\n{...}\n... (NDJSON)
    # Accept both, plus single object and {"logs":[...]} envelope.
    try:
        payload = json.loads(body)
        records = (
            payload if isinstance(payload, list)
            else payload.get("logs") if isinstance(payload, dict) and isinstance(payload.get("logs"), list)
            else [payload] if isinstance(payload, dict)
            else None
        )
    except json.JSONDecodeError:
        # Fall back to NDJSON (Stacked JSON)
        records = []
        for i, line in enumerate(body.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise HTTPException(400, f"invalid json on line {i + 1}: {e}")

    if not isinstance(records, list):
        raise HTTPException(400, "expected array of records")

    t0 = time.time()
    state["sqlite"].insert_many(records)
    if state["loki"]:
        try:
            state["loki"].push_many(records)
        except Exception as e:
            log.warning(f"loki push failed (sqlite still persisted): {e}")

    dt = time.time() - t0
    log.info(f"ingest n={len(records)} bytes={len(body)} took={dt*1000:.0f}ms")
    return Response(status_code=204)
