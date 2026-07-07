import aiosqlite
import json
from datetime import datetime, timezone
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                source TEXT DEFAULT 'api',
                category TEXT,
                priority TEXT DEFAULT 'medium',
                priority_level INTEGER DEFAULT 3,
                status TEXT DEFAULT 'new',
                assigned_agent TEXT,
                root_cause TEXT,
                recommended_action TEXT,
                confidence_score REAL DEFAULT 0.0,
                resolution TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                sla_deadline TEXT,
                metadata TEXT DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS incident_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                agent_id TEXT,
                agent_name TEXT,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (incident_id) REFERENCES incidents(id)
            );
            
            CREATE TABLE IF NOT EXISTS agent_status (
                agent_id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                current_task TEXT,
                tasks_completed INTEGER DEFAULT 0,
                last_active TEXT,
                uptime_seconds REAL DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                pattern TEXT,
                keywords TEXT,
                title TEXT,
                solution TEXT,
                script TEXT,
                confidence REAL DEFAULT 0.8,
                times_used INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 1.0
            );
            
            CREATE TABLE IF NOT EXISTS splunk_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                severity TEXT DEFAULT 'high',
                created_at TEXT NOT NULL
            );
        """)
        await db.commit()


async def reset_incidents():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM incident_timeline")
        await db.execute("DELETE FROM incidents")
        await db.execute("DELETE FROM agent_status")
        await db.commit()


async def execute_query(query, params=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params or ())
        rows = await cursor.fetchall()
        await db.commit()
        return [dict(row) for row in rows]


async def execute_insert(query, params=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params or ())
        await db.commit()
        return cursor.lastrowid


async def execute_update(query, params=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(query, params or ())
        await db.commit()


async def get_incident(incident_id):
    rows = await execute_query("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    return rows[0] if rows else None


async def get_all_incidents():
    return await execute_query("SELECT * FROM incidents ORDER BY created_at DESC")


async def get_incidents_by_status(status):
    return await execute_query("SELECT * FROM incidents WHERE status = ?", (status,))


async def create_incident(incident_data):
    now = datetime.now(timezone.utc).isoformat()
    await execute_insert(
        """INSERT INTO incidents (id, title, description, source, category, priority, priority_level, status, created_at, updated_at, sla_deadline, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)""",
        (
            incident_data["id"],
            incident_data["title"],
            incident_data.get("description", ""),
            incident_data.get("source", "api"),
            incident_data.get("category"),
            incident_data.get("priority", "medium"),
            incident_data.get("priority_level", 3),
            now,
            now,
            incident_data.get("sla_deadline"),
            json.dumps(incident_data.get("metadata", {})),
        ),
    )
    return incident_data["id"]


async def update_incident(incident_id, updates):
    now = datetime.now(timezone.utc).isoformat()
    set_clauses = []
    params = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        params.append(value)
    set_clauses.append("updated_at = ?")
    params.append(now)
    params.append(incident_id)
    await execute_update(
        f"UPDATE incidents SET {', '.join(set_clauses)} WHERE id = ?", params
    )


async def add_timeline_entry(incident_id, agent_id, agent_name, action, details):
    now = datetime.now(timezone.utc).isoformat()
    await execute_insert(
        "INSERT INTO incident_timeline (incident_id, agent_id, agent_name, action, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (incident_id, agent_id, agent_name, action, details, now),
    )


async def get_timeline(incident_id):
    return await execute_query(
        "SELECT * FROM incident_timeline WHERE incident_id = ? ORDER BY timestamp ASC",
        (incident_id,),
    )


async def update_agent_status(agent_id, agent_name, status, current_task=None):
    now = datetime.now(timezone.utc).isoformat()
    await execute_insert(
        """INSERT OR REPLACE INTO agent_status (agent_id, agent_name, status, current_task, last_active, tasks_completed)
           VALUES (?, ?, ?, ?, ?, COALESCE((SELECT tasks_completed FROM agent_status WHERE agent_id = ?), 0))""",
        (agent_id, agent_name, status, current_task, now, agent_id),
    )


async def increment_agent_tasks(agent_id):
    await execute_update(
        "UPDATE agent_status SET tasks_completed = tasks_completed + 1 WHERE agent_id = ?",
        (agent_id,),
    )


async def get_all_agent_statuses():
    return await execute_query("SELECT * FROM agent_status")


async def get_dashboard_stats():
    total = await execute_query(
        "SELECT COUNT(*) as count FROM incidents WHERE status != 'suppressed'"
    )
    by_status = await execute_query(
        "SELECT status, COUNT(*) as count FROM incidents WHERE status != 'suppressed' GROUP BY status"
    )
    by_priority = await execute_query(
        "SELECT priority, COUNT(*) as count FROM incidents WHERE status != 'suppressed' GROUP BY priority"
    )
    by_category = await execute_query(
        "SELECT category, COUNT(*) as count FROM incidents WHERE status != 'suppressed' GROUP BY category"
    )
    resolved = await execute_query(
        "SELECT COUNT(*) as count FROM incidents WHERE status IN ('resolved', 'closed') AND status != 'suppressed'"
    )
    pending_approval = await execute_query(
        "SELECT COUNT(*) as count FROM incidents WHERE status = 'awaiting_approval' AND status != 'suppressed'"
    )
    return {
        "total_incidents": total[0]["count"] if total else 0,
        "resolved": resolved[0]["count"] if resolved else 0,
        "pending_approval": pending_approval[0]["count"] if pending_approval else 0,
        "by_status": {r["status"]: r["count"] for r in by_status},
        "by_priority": {r["priority"]: r["count"] for r in by_priority},
        "by_category": {(r["category"] or "Unknown"): r["count"] for r in by_category},
    }


async def seed_knowledge_base():
    """Seed KB from JSON files if table is empty."""
    count = await execute_query("SELECT COUNT(*) as c FROM knowledge_entries")
    if count[0]["c"] > 0:
        return
    import os
    from config import KB_DIR

    for fname in ["runbooks.json", "sops.json"]:
        fpath = KB_DIR / fname
        if fpath.exists():
            with open(fpath) as f:
                entries = json.load(f)
            for e in entries:
                await execute_insert(
                    "INSERT INTO knowledge_entries (category, pattern, keywords, title, solution, script, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        e.get("category"),
                        e.get("pattern"),
                        json.dumps(e.get("keywords", [])),
                        e["title"],
                        e["solution"],
                        e.get("script"),
                        e.get("confidence", 0.8),
                    ),
                )


async def search_knowledge_base(category=None, keywords=None):
    query = "SELECT * FROM knowledge_entries WHERE 1=1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    rows = await execute_query(query, params)
    if keywords:
        scored = []
        for row in rows:
            entry_kw = json.loads(row.get("keywords", "[]"))
            match_score = sum(
                1 for kw in keywords if any(kw.lower() in ek.lower() for ek in entry_kw)
            )
            if match_score > 0 or not keywords:
                row["match_score"] = match_score
                scored.append(row)
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        return scored
    return rows


async def add_knowledge_entry(
    category, pattern, keywords, title, solution, script, confidence=0.8
):
    await execute_insert(
        "INSERT INTO knowledge_entries (category, pattern, keywords, title, solution, script, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (category, pattern, json.dumps(keywords), title, solution, script, confidence),
    )


async def search_incidents(query):
    query_str = f"%{query}%"
    return await execute_query(
        "SELECT * FROM incidents WHERE id LIKE ? OR title LIKE ? OR description LIKE ? OR root_cause LIKE ? ORDER BY created_at DESC",
        (query_str, query_str, query_str, query_str),
    )


async def seed_splunk_rules():
    count = await execute_query("SELECT COUNT(*) as c FROM splunk_rules")
    if count[0]["c"] > 0:
        return

    default_rules = [
        ("abend", "critical"),
        ("exception", "high"),
        ("fatal", "critical"),
        ("oom", "critical"),
        ("crash", "critical"),
        ("failed", "high"),
        ("timeout", "high"),
        ("error", "high"),
    ]

    now = datetime.now(timezone.utc).isoformat()
    for kw, sev in default_rules:
        try:
            await execute_insert(
                "INSERT INTO splunk_rules (keyword, severity, created_at) VALUES (?, ?, ?)",
                (kw, sev, now),
            )
        except Exception:
            pass


async def get_splunk_rules():
    return await execute_query("SELECT * FROM splunk_rules ORDER BY keyword ASC")


async def add_splunk_rule(keyword, severity="high"):
    now = datetime.now(timezone.utc).isoformat()
    return await execute_insert(
        "INSERT INTO splunk_rules (keyword, severity, created_at) VALUES (?, ?, ?)",
        (keyword.lower().strip(), severity, now),
    )


async def delete_splunk_rule(rule_id):
    await execute_update("DELETE FROM splunk_rules WHERE id = ?", (rule_id,))
