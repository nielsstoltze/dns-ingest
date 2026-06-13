# dns-ingest

DNS Resolver log receiver for **Strata Logging Service** HTTPS forwarding.

PANW's Advanced DNS Security cloud-resolver logs every DNS transaction into
SLS. SLS does not expose a query API for non-XSOAR tenants, so we ship the
logs straight back out via the HTTPS forwarding profile and consume them
on our own collector.

## Flow

```
SLS (Advanced DNS Security cloud)
  └─ HTTPS forwarding profile (gzip JSON batches, ≤500 records each)
       → https://dns-logs.hoej.eu/v1/ingest
            └─ chost11 nginx-tls (wildcard cert, mTLS optional)
                 → app81:8093 (this service)
                      ├─ SQLite (/var/lib/dns-ingest/dns.sqlite) — SQL ad-hoc
                      └─ Loki    — live tail / Grafana dashboards
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/v1/ingest` | SLS HTTPS sink. Accepts gzip or plain JSON; array of records or `{"logs":[...]}` |
| `GET`  | `/health`    | `{"ok": true, "rows": N, "loki": bool}` |

## Layout

| Path | Role |
|---|---|
| `app/main.py`         | FastAPI app + ingest endpoint |
| `app/storage_sqlite.py` | SQLite store with narrow indexed columns + `raw` JSON |
| `app/storage_loki.py`   | Optional Loki push (one stream per `src` to bound cardinality) |
| `systemd/dns-ingest.service` | app81 systemd unit (port 8093, behind nginx-tls) |
| `nginx/dns-logs.hoej.eu.conf` | chost11 vhost |
| `tests/fake_batch.py` | Smoke-test client |

## Deploy

```bash
ssh app81
cd ~/dns-ingest
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp dns-ingest.env.example dns-ingest.env  # edit if Loki is on
sudo install -m 644 systemd/dns-ingest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dns-ingest
```

## Configure SLS forwarding (manual, SCM → Strata Logging Service)

1. SCM → Logs → **Log Forwarding** → Add
2. Log type: **DNS Security** (or **Threat** with subtype filter `dns`)
3. Destination type: **HTTPS**
4. URL: `https://dns-logs.hoej.eu/v1/ingest`
5. Format: **JSON**, compression: **gzip**
6. Client cert (optional, mTLS): import HOEJ-issued client cert; trust on
   the nginx side via `nginx/dns-logs.hoej.eu.conf`
7. Save + commit

Verify with `tests/fake_batch.py` first to make sure the receiver answers
204 before SLS hits it.
