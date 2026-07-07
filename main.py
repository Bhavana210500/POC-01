import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

# Load .env FIRST — before any module reads os.getenv()
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

import asyncio
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from config import STATIC_DIR, AGENT_CONFIG
from database import (
    init_db,
    reset_incidents,
    seed_knowledge_base,
    get_all_incidents,
    get_incident,
    get_timeline,
    get_all_agent_statuses,
    get_dashboard_stats,
    get_incidents_by_status,
    update_incident,
    add_timeline_entry,
    search_incidents,
)
from orchestrator import orchestrator
from agents.ticket_creator import TicketCreatorAgent
from agents.root_cause_investigator import RootCauseInvestigator
from agents.knowledge_base_agent import KnowledgeBaseAgent
from agents.self_healing_agent import SelfHealingAgent
from agents.remediation_agent import RemediationAgent
from simulator import generate_alert, generate_batch

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("helix")


async def run_splunk_pull_task():
    """Background task: polls Splunk REST API (or mock logs) on a configurable interval."""
    from splunk_pull_scheduler import (
        SPLUNK_CONFIG,
        fetch_splunk_logs_mock,
        fetch_splunk_logs_real,
        forward_to_helix,
        log,
    )

    log("Splunk background pull task started.")

    while True:
        try:
            loop = asyncio.get_running_loop()
            is_mock = SPLUNK_CONFIG["is_mock"]

            if is_mock:
                events = await loop.run_in_executor(None, fetch_splunk_logs_mock)
            else:
                events = await loop.run_in_executor(None, fetch_splunk_logs_real)

            if events:
                await loop.run_in_executor(None, forward_to_helix, events)
        except asyncio.CancelledError:
            log("Splunk pull task cancelled.")
            break
        except Exception as e:
            log(f"Error in Splunk pull loop: {e}")

        interval = SPLUNK_CONFIG.get("poll_interval", 300)
        await asyncio.sleep(interval)


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Helix AIOps Platform...")
    await init_db()
    await seed_knowledge_base()

    # Initialize and train ML Model
    logger.info("Initializing offline ML Model...")
    from ml_model import ml_model

    ml_model.load_training_data()
    ml_model.train()
    logger.info(
        f"ML Model trained with {len(ml_model.training_data)} historical entries."
    )

    # Register agents
    orchestrator.register_agent("agent-01", TicketCreatorAgent())
    orchestrator.register_agent("agent-02", RootCauseInvestigator())
    orchestrator.register_agent("agent-03", KnowledgeBaseAgent())
    orchestrator.register_agent("agent-04", SelfHealingAgent())
    orchestrator.register_agent("agent-05", RemediationAgent())

    # Start orchestrator in background
    orchestrator_task = asyncio.create_task(orchestrator.start())

    # Start the Splunk pull scheduler in background
    splunk_task = asyncio.create_task(run_splunk_pull_task())

    logger.info("Helix AIOps Platform is READY")

    yield

    # Shutdown
    await orchestrator.stop()
    splunk_task.cancel()
    orchestrator_task.cancel()
    logger.info("Helix AIOps Platform shutdown complete")


app = FastAPI(
    title="Helix AIOps Platform",
    description="Multi-Agent IT Incident Automation",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# === API ROUTES ===


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(str(index_path))


@app.post("/api/alerts")
async def ingest_alert(request: Request):
    """Ingest a new alert into the pipeline."""
    body = await request.json()
    await orchestrator.submit_incident(body)
    return {"status": "accepted", "message": "Alert queued for processing"}


@app.get("/api/webhooks/splunk")
async def splunk_webhook_info():
    """Return friendly message explaining how to invoke the Splunk Webhook."""
    return {
        "status": "active",
        "endpoint": "/api/webhooks/splunk",
        "method_allowed": "POST",
        "description": "This endpoint receives alert webhooks from Splunk. Send a POST request with JSON payload.",
        "usage_instructions": {
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "sample_payload": {
                "search_name": "Splunk Alert",
                "result": {
                    "_raw": "2026-06-23 15:00:00 [ERROR] host-01 database connection failed",
                    "host": "host-01",
                    "source": "splunk_webhook",
                },
            },
        },
    }


@app.post("/api/webhooks/splunk")
async def splunk_webhook(request: Request):
    """Receive alerts from Splunk Webhook Alert Actions."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload from Splunk")

    result = body.get("result", {})
    search_name = body.get("search_name", "Splunk Alert")

    raw_event = result.get("_raw", "")
    host = result.get("host", "unknown-host")

    severity = (
        "critical"
        if any(k in raw_event.lower() for k in ["abend", "fatal", "crash", "oom"])
        else "high"
    )

    alert = {
        "title": f"Splunk Alert: {search_name}",
        "description": f"Host: {host}\nRaw Event: {raw_event}",
        "source": "splunk",
        "severity": severity,
        "host": host,
        "metric": "splunk_alert",
        "value": 1,
        "threshold": 0,
        "tags": [search_name.lower().replace(" ", "_"), "splunk"],
    }

    await orchestrator.submit_incident(alert)
    return {"status": "success", "message": "Splunk webhook ingested successfully"}


@app.post("/api/splunk/proxy-poll")
async def proxy_splunk_poll(request: Request):
    """Proxy endpoint to poll Splunk REST API from the UI dashboard."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    mode = body.get("mode", "real")

    if mode == "real":
        splunk_url = body.get("splunk_url", "")
        token = body.get("token", "")
        auth_type = body.get("auth_type", "bearer")
        query = body.get("query", "search index=main (error OR fail OR abend OR crash)")

        if not splunk_url:
            raise HTTPException(status_code=400, detail="Splunk URL is required")

        headers = {}
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "splunk":
            headers["Authorization"] = f"Splunk {token}"
        elif auth_type == "basic":
            import base64

            encoded = base64.b64encode(token.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        try:
            import httpx

            base_clean = splunk_url.replace(":8089", "").rstrip("/")
            candidate_urls = []
            if "splunkcloud.com" in base_clean and "api-" not in base_clean:
                parts = base_clean.split("//")
                if len(parts) == 2:
                    api_sub = f"{parts[0]}//api-{parts[1]}"
                    candidate_urls.append(f"{api_sub}/services/search/jobs/export")
                    candidate_urls.append(f"{api_sub}:8089/services/search/jobs/export")

            candidate_urls.append(
                f"{splunk_url.rstrip('/')}/services/search/jobs/export"
            )
            candidate_urls.append(f"{base_clean}:8089/services/search/jobs/export")
            candidate_urls.append(f"{base_clean}/services/search/jobs/export")

            candidate_urls = list(dict.fromkeys(candidate_urls))

            data = {
                "search": query,
                "output_mode": "json",
                "earliest_time": "-4h",
                "latest_time": "now",
            }

            success = False
            events = []
            last_err = None

            for curl in candidate_urls:
                if success:
                    break
                for trust in [False, True]:
                    try:
                        logger.info(
                            f"Attempting Splunk API fetch at: {curl} (trust_env={trust})"
                        )
                        async with httpx.AsyncClient(
                            verify=False, trust_env=trust, follow_redirects=True
                        ) as client:
                            res = await client.post(
                                curl, data=data, headers=headers, timeout=3.5
                            )
                        if (
                            res.status_code == 200
                            and not res.text.strip().lower().startswith("<!doc")
                            and not res.text.strip().lower().startswith("<html")
                        ):
                            for line in res.text.strip().split("\n"):
                                if not line.strip():
                                    continue
                                try:
                                    event_data = json.loads(line)
                                    result = event_data.get("result", {})
                                    if result:
                                        events.append(result)
                                except Exception:
                                    pass
                            success = True
                            logger.info(
                                f"Successfully connected to Splunk API at {curl}! Retrieved {len(events)} events."
                            )
                            break
                        else:
                            last_err = f"HTTP {res.status_code}: {res.text[:100]}"
                    except Exception as e:
                        last_err = f"{type(e).__name__}: {e}"

            if success:
                return {"events": events, "new_offset": 0, "simulated": False}
            else:
                logger.warning(
                    f"All direct Splunk API attempts failed. Last error: {last_err}. Using dynamic testfile.log simulation."
                )
                from splunk_pull_scheduler import fetch_splunk_logs_mock

                last_offset = body.get("last_line_offset", 0)
                mock_events = fetch_splunk_logs_mock(custom_offset=last_offset)
                new_offset = last_offset + len(mock_events)
                return {
                    "events": mock_events,
                    "new_offset": new_offset,
                    "simulated": True,
                }
        except HTTPException as he:
            logger.error(f"Splunk proxy poll HTTP exception: {he.detail}")
            raise
        except Exception as e:
            logger.warning(
                f"Splunk proxy poll connection failed ({type(e).__name__}: {e}). Using dynamic testfile.log simulation."
            )
            from splunk_pull_scheduler import fetch_splunk_logs_mock

            last_offset = body.get("last_line_offset", 0)
            mock_events = fetch_splunk_logs_mock(custom_offset=last_offset)
            new_offset = last_offset + len(mock_events)
            return {"events": mock_events, "new_offset": new_offset, "simulated": True}
    else:
        raise HTTPException(
            status_code=400,
            detail="Only 'real' mode is supported. Configure Splunk credentials in Settings.",
        )


@app.post("/api/simulate")
async def simulate_alert(request: Request):
    """Simulate an alert for demo purposes."""
    body = await request.json() if await request.body() else {}
    count = body.get("count", 1)
    template_index = body.get("template_index")

    alerts = []
    for i in range(min(count, 5)):
        if template_index is not None:
            alert = generate_alert(template_index)
        else:
            alert = generate_alert()
        await orchestrator.submit_incident(alert)
        alerts.append(alert)

    return {"status": "simulated", "count": len(alerts), "alerts": alerts}


@app.get("/api/tickets")
async def list_tickets(status: str = None):
    """List all tickets, optionally filtered by status. Excludes suppressed tickets by default."""
    if status:
        incidents = await get_incidents_by_status(status)
    else:
        all_incidents = await get_all_incidents()
        incidents = [i for i in all_incidents if i.get("status") != "suppressed"]
    return {"tickets": incidents, "count": len(incidents)}


@app.get("/api/tickets/search")
async def search_tickets(q: str):
    """Search for historical incidents by keyword."""
    if not q:
        return {"tickets": [], "count": 0}
    incidents = await search_incidents(q)
    return {"tickets": incidents, "count": len(incidents)}


@app.get("/api/tickets/{incident_id}")
async def get_ticket(incident_id: str):
    """Get full ticket detail with timeline."""
    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    timeline = await get_timeline(incident_id)
    return {"ticket": incident, "timeline": timeline}


@app.post("/api/tickets/{incident_id}/approve")
async def approve_ticket(incident_id: str, request: Request):
    """Approve or reject a ticket for remediation."""
    body = await request.json()
    approved = body.get("approved", False)
    comment = body.get("comment", "")
    remediation_steps = body.get("remediation_steps", "")
    remediation_type = body.get("remediation_type", "text")

    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Incident is not awaiting approval (current: {incident['status']})",
        )

    await orchestrator.handle_approval_response(
        incident_id, approved, comment, remediation_steps, remediation_type
    )
    action = "approved" if approved else "rejected"
    return {"status": action, "incident_id": incident_id}


@app.post("/api/tickets/{incident_id}/root_cause_feedback")
async def root_cause_feedback(incident_id: str, request: Request):
    """Handle user feedback on the predicted root cause."""
    body = await request.json()
    is_correct = body.get("is_correct", True)
    correct_root_cause = body.get("correct_root_cause", "")

    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    from database import execute_update, execute_insert
    import json

    # Store feedback in incident metadata
    metadata = json.loads(incident.get("metadata") or "{}")
    metadata["root_cause_feedback"] = {
        "is_correct": is_correct,
        "correct_root_cause": correct_root_cause,
    }

    # Update incident with correct root cause if provided
    actual_root_cause = incident.get("root_cause", "")
    if not is_correct and correct_root_cause:
        actual_root_cause = correct_root_cause
        await execute_update(
            "UPDATE incidents SET root_cause = ?, metadata = ? WHERE id = ?",
            (actual_root_cause, json.dumps(metadata), incident_id),
        )
    else:
        await execute_update(
            "UPDATE incidents SET metadata = ? WHERE id = ?",
            (json.dumps(metadata), incident_id),
        )

    # Feed the verified data back into the ML model for continuous learning
    from ml_model import MLModel

    model = MLModel()
    model.add_new_incident(
        category=incident.get("category", "Unknown"),
        title=incident.get("title", ""),
        description=incident.get("description", ""),
        root_cause=actual_root_cause,
        resolution=incident.get("resolution", ""),
        script="",
    )

    return {"status": "success", "message": "Feedback recorded and ML model updated."}


@app.get("/api/agents/status")
async def agent_status():
    """Get status of all agents."""
    statuses = await get_all_agent_statuses()
    return {"agents": statuses}


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    """Get dashboard statistics."""
    stats = await get_dashboard_stats()
    agents = await get_all_agent_statuses()
    stats["agents"] = agents
    return stats


@app.get("/api/config/splunk")
async def get_splunk_config():
    """Get current Splunk configuration (tokens are masked)."""
    from splunk_pull_scheduler import SPLUNK_CONFIG

    config_copy = dict(SPLUNK_CONFIG)
    if config_copy.get("password"):
        config_copy["password"] = "********"
    if config_copy.get("token"):
        config_copy["token"] = "********"
    return config_copy


@app.post("/api/config/splunk/test")
async def test_splunk_conn(request: Request):
    """Test Splunk REST API connectivity with provided credentials."""
    from splunk_pull_scheduler import test_splunk_connection, SPLUNK_CONFIG

    body = await request.json()

    api_url = body.get("api_url", "")
    auth_method = body.get("auth_method", "token")
    token = body.get("token", "")
    username = body.get("username", "")
    password = body.get("password", "")
    query = body.get("query", "")
    poll_interval = int(body.get("poll_interval", 300))

    if auth_method == "token" and token == "********":
        token = SPLUNK_CONFIG["token"]
    if auth_method == "basic" and password == "********":
        password = SPLUNK_CONFIG["password"]

    success, message = test_splunk_connection(
        api_url=api_url,
        auth_method=auth_method,
        token=token,
        username=username,
        password=password,
        query=query,
        poll_interval=poll_interval,
    )
    return {"success": success, "message": message}


@app.post("/api/config/splunk/save")
async def save_splunk_config(request: Request):
    """Save Splunk configuration in-memory (takes effect immediately)."""
    from splunk_pull_scheduler import SPLUNK_CONFIG

    body = await request.json()

    api_url = body.get("api_url", "")
    auth_method = body.get("auth_method", "token")
    token = body.get("token", "")
    username = body.get("username", "")
    password = body.get("password", "")
    query = body.get(
        "query",
        "search index=main sourcetype=syslog (error OR fail OR fatal OR abend OR crash)",
    )
    earliest_time = body.get("earliest_time", "-5m")
    poll_interval = int(body.get("poll_interval", 300))

    if auth_method == "token" and token == "********":
        token = SPLUNK_CONFIG["token"]
    if auth_method == "basic" and password == "********":
        password = SPLUNK_CONFIG["password"]

    SPLUNK_CONFIG["api_url"] = api_url
    SPLUNK_CONFIG["auth_method"] = auth_method
    SPLUNK_CONFIG["token"] = token
    SPLUNK_CONFIG["username"] = username
    SPLUNK_CONFIG["password"] = password
    SPLUNK_CONFIG["query"] = query
    SPLUNK_CONFIG["earliest_time"] = earliest_time
    SPLUNK_CONFIG["poll_interval"] = poll_interval

    has_creds = api_url and (token or (username and password))
    SPLUNK_CONFIG["is_mock"] = not has_creds

    return {
        "status": "success",
        "message": f"Splunk configuration saved. Poll interval: {poll_interval}s.",
        "is_mock": SPLUNK_CONFIG["is_mock"],
    }


@app.get("/api/alerts/templates")
async def list_alert_templates():
    """List available alert simulation templates."""
    from simulator import ALERT_TEMPLATES

    return {
        "templates": [
            {"index": i, "title": t["title"], "severity": t["severity"]}
            for i, t in enumerate(ALERT_TEMPLATES)
        ]
    }


# === DATABASE BROWSER ENDPOINTS ===


@app.get("/db", response_class=HTMLResponse)
async def db_viewer():
    """Serve the database viewer dashboard page."""
    db_html_path = STATIC_DIR / "db.html"
    return FileResponse(str(db_html_path))


@app.get("/api/db/tables")
async def api_get_db_tables():
    """List all tables in the SQLite database along with row counts and schemas."""
    import aiosqlite
    import os
    from config import DB_PATH

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row["name"] for row in await cursor.fetchall()]

            result = []
            for table in tables:
                count_cursor = await db.execute(
                    f"SELECT COUNT(*) as count FROM {table}"
                )
                count_row = await count_cursor.fetchone()
                row_count = count_row["count"] if count_row else 0

                schema_cursor = await db.execute(f"PRAGMA table_info({table});")
                columns = [dict(col) for col in await schema_cursor.fetchall()]

                result.append(
                    {"name": table, "row_count": row_count, "columns": columns}
                )

            db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
            version_cursor = await db.execute("select sqlite_version();")
            version_row = await version_cursor.fetchone()
            sqlite_version = version_row[0] if version_row else "Unknown"

            return {
                "tables": result,
                "sqlite_version": sqlite_version,
                "database_size_bytes": db_size,
                "database_path": str(DB_PATH),
            }
    except Exception as e:
        logger.error(f"Error fetching database tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/table/{table_name}")
async def api_get_db_table_data(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    search: str = None,
    sort_by: str = None,
    sort_order: str = "desc",
):
    """Get rows from a specific table with basic pagination and search."""
    import aiosqlite
    from config import DB_PATH

    valid_tables = [
        "incidents",
        "incident_timeline",
        "agent_status",
        "knowledge_entries",
        "splunk_rules",
    ]
    if table_name not in valid_tables:
        raise HTTPException(status_code=400, detail="Invalid table name")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            schema_cursor = await db.execute(f"PRAGMA table_info({table_name});")
            columns = [col["name"] for col in await schema_cursor.fetchall()]

            query = f"SELECT * FROM {table_name}"
            params = []

            if search and columns:
                search_clauses = []
                for col in columns:
                    search_clauses.append(f"CAST({col} AS TEXT) LIKE ?")
                    params.append(f"%{search}%")
                query += " WHERE " + " OR ".join(search_clauses)

            if sort_by and sort_by in columns:
                order = "DESC" if sort_order.lower() == "desc" else "ASC"
                query += f" ORDER BY {sort_by} {order}"
            elif "id" in columns:
                query += " ORDER BY id DESC"
            elif "created_at" in columns:
                query += " ORDER BY created_at DESC"
            elif "timestamp" in columns:
                query += " ORDER BY timestamp DESC"

            count_query = f"SELECT COUNT(*) as count FROM ({query})"
            count_cursor = await db.execute(count_query, params)
            count_row = await count_cursor.fetchone()
            total_count = count_row["count"] if count_row else 0

            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await db.execute(query, params)
            rows = [dict(row) for row in await cursor.fetchall()]

            return {
                "table": table_name,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "rows": rows,
            }
    except Exception as e:
        logger.error(f"Error fetching table data for {table_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/query")
async def api_execute_custom_query(request: Request):
    """Execute raw SQL statements against the SQLite database."""
    import aiosqlite
    from config import DB_PATH

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    sql = body.get("query", "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    is_select = any(
        sql.upper().startswith(kw) for kw in ["SELECT", "PRAGMA", "EXPLAIN", "WITH"]
    )

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql)

            if is_select:
                rows = [dict(row) for row in await cursor.fetchall()]
                await db.commit()
                return {
                    "status": "success",
                    "type": "select",
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": rows,
                    "row_count": len(rows),
                    "message": f"Query returned {len(rows)} row(s).",
                }
            else:
                affected = db.total_changes
                await db.commit()
                return {
                    "status": "success",
                    "type": "write",
                    "affected_rows": affected,
                    "message": f"Statement executed successfully. Affected rows (total changes): {affected}.",
                }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/db/reset")
async def api_reset_db():
    """Reset the database and re-seed all initial data."""
    try:
        from database import reset_incidents, seed_knowledge_base, seed_splunk_rules

        await reset_incidents()
        await seed_knowledge_base()
        await seed_splunk_rules()
        return {
            "status": "success",
            "message": "Database reset and seeded successfully.",
        }
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
