# Runbook — SLS HTTPS forwarding to dns-ingest

Configures the Strata Logging Service to push DNS Resolver logs to our
local receiver at `https://dns-logs.hoej.eu/v1/ingest`.

Time: ~5 minutes. Reversible — disable the profile to stop.

## Prereqs (already done)

- [x] Receiver running on app81:8093 (`systemctl --user status dns-ingest`)
- [x] UFW rule for 8093 (`sudo ufw status | grep 8093`)
- [x] chost11 nginx-tls vhost `dns-logs.hoej.eu` → app81:8093
- [x] AdGuard rewrite `dns-logs.hoej.eu → 100.67.5.11`
- [x] Wildcard `*.hoej.eu` cert valid (test: `curl -sS https://dns-logs.hoej.eu/health`)

## Steps in SCM

1. Sign in to **Strata Cloud Manager** → **Manage → Configuration →
   Strata Logging Service → Log Forwarding**
2. Click **Add** → **HTTPS**
3. Profile name: `dns-logs-hoej-eu`
4. URL: `https://dns-logs.hoej.eu/v1/ingest`
5. Method: `POST`
6. Payload format: **JSON**, compression: **GZIP**
7. Batch size: **500** (or platform default)
8. Authentication:
   - **None** if you trust the wildcard cert chain (lab default)
   - **Client cert** if you want mTLS — issue from HOEJ Root CA 2046
     and import on both ends; add `ssl_verify_client on; ssl_client_certificate /etc/nginx/ca.pem;`
     to the vhost
9. Certificate validation: **enabled** (wildcard `*.hoej.eu` is publicly
   trusted via Cloudflare/Let's Encrypt — verify chain works)
10. Filter / Match-list:
    - Log type: **DNS Security**
    - Filter: leave wide-open initially; tighten once we see traffic
11. **Save** → **Commit**

## Verify

After commit, watch the receiver:

```bash
ssh app81 'journalctl --user -u dns-ingest -f'
# expect log lines: "ingest n=<N> bytes=<B> took=<MS>ms"
```

And SQL:

```bash
sqlite3 /home/local_admin/dns-ingest/data/dns.sqlite \
    "SELECT COUNT(*), MIN(log_time), MAX(log_time) FROM dns_logs"
```

If rows stop appearing after a known-active burst, check:

- SCM Log Forwarding profile → **Statistics** (drops / send-failures)
- nginx access log on chost11: `docker logs nginx-tls 2>&1 | grep dns-logs`
- receiver health: `curl https://dns-logs.hoej.eu/health`

## Rollback

In SCM, disable or delete the `dns-logs-hoej-eu` HTTPS profile. SLS
keeps the logs internally (Explore/Log Viewer still works) — only the
push to our receiver stops.
