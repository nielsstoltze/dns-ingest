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

This is two screens, not one.

### Step 1 — Define the HTTPS server profile (transport)

SCM → **Manage → Configuration → Strata Logging Service → Log
Forwarding → HTTPS Server Profile → Add**

| Field | Value |
|---|---|
| NAME | `dns-logs-hoej-eu` |
| URL  | `https://dns-logs.hoej.eu/v1/ingest` |
| PROFILE TYPE | `Log Forwarding` (locked) |
| Server Authentication → CERTIFICATE DETAILS | **Public CAs** — leave empty, do not upload anything. Our `*.hoej.eu` wildcard chains to a public CA |
| Client Authentication | Leave empty — we do not run mTLS on the nginx side |
| Client Authorization → TYPE | **None** — we are not Splunk HEC, Sentinel, Chronicle or Exabeam |

Click **Test Connection**. Expect a TLS handshake to succeed and a
non-error HTTP code (the receiver returns `405` for GET on `/v1/ingest`
or `204` if SCM happens to POST; both prove the path works).

### Step 2 — Attach a match-list (which logs go through that transport)

SCM → **Strata Logging Service → Log Forwarding** (the profile screen,
not the server-profile screen).

1. Add a match-list / forwarding rule
2. Log type: **DNS Security** (or **Threat** with subtype filter `dns`
   if DNS Security log-type isn't exposed yet on this tenant)
3. Payload format: **JSON**, compression: **GZIP** if exposed
4. Destination: the `dns-logs-hoej-eu` server profile from Step 1
5. Filter: leave wide-open at first; tighten once we see real traffic

### Step 3 — Commit

Save → Commit on the tenant.

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
