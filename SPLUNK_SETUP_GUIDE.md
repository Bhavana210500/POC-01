# Splunk Setup Guide — Helix AIOps Platform

## Quick Start

### 1. Configure Credentials

Open the **`.env`** file in the project root and fill in your Splunk details:

```env
# Your Splunk Cloud REST API URL (port 8089) — ask Nordea for this
SPLUNK_API_URL=https://<tenant>.api.splunkcloud.com:8089

# Splunk Auth Token (JWT) — already provided, set in .env
SPLUNK_TOKEN=<your-jwt-token>

# SPL query — change this to match your log index/sourcetype
SPLUNK_QUERY=search index=main sourcetype=syslog (error OR fail OR fatal OR abend OR crash)

# Poll every 5 minutes
SPLUNK_POLL_INTERVAL=300
```

> **Token Type:** Your token is a **Splunk REST API Auth Token (JWT)**, not an HEC token.
> HEC tokens push data INTO Splunk. Auth tokens PULL/search data FROM Splunk — which is what we need.
> The token is sent as `Authorization: Bearer <token>` on every Splunk REST API request.

> **⚠️ Token Expiry:** Your current token expires around **July 28, 2026** (~30 days).
> You'll need to request a new token from Nordea before it expires.

### 2. Start the Server

```bash
python main.py
```

The server starts at **http://localhost:8000** (or the custom port you configured using `PORT` in your `.env` file). You will see:
```
Helix AIOps Platform is READY
Splunk background pull task started.
```

### 3. Verify Logs Are Being Pulled

- Open **http://localhost:8000** (or your configured port) in your browser
- Watch the **Dashboard** — new incidents will appear automatically as Splunk logs are pulled
- Check the terminal for `[SPLUNK_PULL]` messages showing poll activity


---

## Where to Change Each Setting

| What | Where | How |
|------|-------|-----|
| **Splunk URL** | `.env` → `SPLUNK_API_URL` | Splunk REST API URL with port 8089 |
| **HEC Token** | `.env` → `SPLUNK_TOKEN` | Nordea's single HEC Bearer token |
| **Username/Password** | `.env` → `SPLUNK_USERNAME` / `SPLUNK_PASSWORD` | Alternative to token auth |
| **SPL Query** | `.env` → `SPLUNK_QUERY` | The search query that pulls logs |
| **Poll Interval** | `.env` → `SPLUNK_POLL_INTERVAL` | Seconds between polls (300 = 5 min) |
| **Server Port** | `.env` → `PORT` | Local application port (default 8000; change if blocked) |

> **Live changes:** You can also change all of these at runtime via the **Dashboard UI**:
> Settings → Splunk Configuration → Test Connection → Save

---

## Changing the SPL Query

The `SPLUNK_QUERY` controls which logs get pulled. Common examples:

```spl
# Pull all errors from main index
search index=main sourcetype=syslog (error OR fail OR fatal OR abend OR crash)

# Pull from a specific index and host
search index=production host=web-svr-* (error OR timeout OR exception)

# Pull application logs
search index=app_logs sourcetype=json level=ERROR earliest=-5m

# Pull security events
search index=security sourcetype=syslog (failed OR unauthorized OR brute)
```

Edit the query in `.env` and **restart the server**, or change it live via the Dashboard UI.

---

## Authentication

### Current (POC Demo)
- **Splunk Auth Token (JWT)** — set in `SPLUNK_TOKEN` in `.env`
- The system sends: `Authorization: Bearer <token>` on every Splunk REST API search request
- This token authenticates as `sc_admin` and is authorized to fetch logs
- **Expires ~July 28, 2026** — request a renewal from Nordea before then

### Future (Nordea Production)
- Nordea uses their own authentication flow to access Splunk
- Once approved, we add a middleware layer that:
  1. Authenticates via Nordea's identity provider
  2. Obtains a session token
  3. Uses that token for Splunk REST API requests
- The core pipeline code stays the same — only the auth layer changes

### BMC Helix ITSM (Production)
- The BMC Helix connector is already in the code (`bmc_helix_connector.py`)
- Currently runs in **mock mode** (`HELIX_MOCK_MODE=True`)
- To connect to real BMC Helix ITSM:
  1. Set `HELIX_MOCK_MODE=False` in `.env`
  2. Set `HELIX_API_URL`, `HELIX_USERNAME`, `HELIX_PASSWORD`
  3. Tickets will be created in both local DB and BMC Helix

---

## Architecture

```
┌──────────────────┐     Every 5 min      ┌──────────────────┐
│   Splunk Cloud   │ ◄──────────────────── │  Poll Scheduler  │
│   REST API       │ ──────────────────► │  (background)    │
│   (port 8089)    │     JSON events      │                  │
└──────────────────┘                      └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │  Helix Webhook   │
                                          │  /api/webhooks/  │
                                          │  splunk          │
                                          └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │  Agent Pipeline  │
                                          │  1. Ticket       │
                                          │  2. Root Cause   │
                                          │  3. Knowledge    │
                                          │  4. Self-Heal    │
                                          │  5. Remediation  │
                                          └──────────────────┘
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No events appearing | Check `SPLUNK_QUERY` returns results when run in Splunk UI |
| Connection timeout | Verify the URL uses port 8089 (REST API), not 443 (Web UI) |
| HTTP 401 | Token is invalid or expired — get a new HEC token |
| HTTP 403 | Token lacks REST API search permissions |
| Mock mode running | Fill in `SPLUNK_API_URL` and `SPLUNK_TOKEN` in `.env` and restart |
