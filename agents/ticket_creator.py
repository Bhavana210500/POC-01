import uuid
import json
from datetime import datetime, timezone, timedelta
from agents.base_agent import BaseAgent
from config import PRIORITY_MAP, CATEGORIES


class TicketCreatorAgent(BaseAgent):
    """Agent 1: Creates and triages incident tickets from raw alerts."""

    SEVERITY_TO_PRIORITY = {
        "critical": "critical",
        "high": "high",
        "warning": "medium",
        "medium": "medium",
        "low": "low",
        "info": "low",
    }

    KEYWORD_CATEGORIES = {
        "Infrastructure": [
            "cpu",
            "memory",
            "disk",
            "server",
            "hardware",
            "vm",
            "host",
            "pod",
            "kubernetes",
            "container",
            "oom",
        ],
        "Application": [
            "application",
            "service",
            "api",
            "response",
            "error",
            "crash",
            "timeout",
            "latency",
            "performance",
            "apm",
        ],
        "Network": [
            "network",
            "latency",
            "packet",
            "dns",
            "firewall",
            "router",
            "switch",
            "bandwidth",
            "datacenter",
        ],
        "Security": [
            "security",
            "login",
            "ssh",
            "brute",
            "attack",
            "ssl",
            "certificate",
            "vulnerability",
            "siem",
            "failed_login",
        ],
        "Database": [
            "database",
            "db",
            "connection",
            "pool",
            "query",
            "replication",
            "sql",
            "postgres",
            "mysql",
            "mongo",
        ],
        "Cloud": ["aws", "azure", "gcp", "cloud", "s3", "ec2", "lambda", "function"],
    }

    def __init__(self):
        super().__init__("agent-01", "Ticket Creator Agent")

    def _is_ticket_needed(self, alert_data):
        """Check if an alert requires an incident ticket. Returns (bool, reason_string)."""
        host = alert_data.get("host", "unknown-host").lower()
        title = alert_data.get("title", "").lower()
        desc = alert_data.get("description", "").lower()

        non_prod_keywords = [
            "dev",
            "stage",
            "demo",
            "sandbox",
            "non-prod",
            "development",
        ]

        # Check host name
        for kw in non_prod_keywords:
            if kw in host:
                return False, f"Non-production host pattern matched: '{kw}'"

        # Check title and description
        for kw in non_prod_keywords:
            if kw in title or kw in desc:
                return False, f"Non-production alert text matched: '{kw}'"

        return True, ""

    def _categorize(self, alert_data):
        """NLP-powered classification of categories using the local ML engine."""
        from ml_model import ml_model

        title = alert_data.get("title", "")
        description = alert_data.get("description", "")
        category, confidence = ml_model.predict_category(title, description)
        return category

    def _prioritize(self, alert_data):
        """Determine priority based on severity and impact."""
        severity = alert_data.get("severity", "medium").lower()
        priority = self.SEVERITY_TO_PRIORITY.get(severity, "medium")

        # Boost priority if value significantly exceeds threshold
        value = alert_data.get("value", 0)
        threshold = alert_data.get("threshold", 0)
        if threshold > 0 and value > threshold * 1.5:
            priority_levels = ["low", "medium", "high", "critical"]
            idx = priority_levels.index(priority)
            if idx < len(priority_levels) - 1:
                priority = priority_levels[idx + 1]

        return priority

    async def process(self, alert_data) -> str:
        """Create a ticket from an alert."""
        from database import (
            create_incident,
            update_incident,
            execute_query,
            add_timeline_entry,
        )

        # 1. Alert Deduplication check
        title = alert_data.get("title", "Unknown Alert")
        host = alert_data.get("host", "unknown-host")

        active_tickets = await execute_query(
            "SELECT id, title, description, metadata FROM incidents WHERE status NOT IN ('resolved', 'closed', 'suppressed')"
        )
        for ticket in active_tickets:
            meta = json.loads(ticket.get("metadata", "{}") or "{}")
            if (
                ticket["title"] == title
                and meta.get("host") == host
                and ticket.get("description") == alert_data.get("description")
            ):
                duplicate_id = ticket["id"]
                raw_event = alert_data.get("description", "No details")
                await add_timeline_entry(
                    duplicate_id,
                    "system",
                    "Ticket Creator Agent",
                    "duplicate_suppressed",
                    f"[DEDUPLICATION] Suppressed new ticket. Correlated duplicate alert from host '{host}'. Event: {raw_event}",
                )
                self.logger.info(
                    f"Alert deduplicated. Correlated with active incident {duplicate_id}"
                )
                return None

        # 2. Check if a ticket is needed (e.g., non-prod filter)
        is_needed, reason = self._is_ticket_needed(alert_data)

        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        category = self._categorize(alert_data)
        priority = self._prioritize(alert_data)
        priority_config = PRIORITY_MAP.get(priority, PRIORITY_MAP["medium"])

        sla_deadline = (
            datetime.now(timezone.utc)
            + timedelta(minutes=priority_config["sla_minutes"])
        ).isoformat()

        incident_data = {
            "id": incident_id,
            "title": alert_data.get("title", "Unknown Alert"),
            "description": alert_data.get("description", ""),
            "source": alert_data.get("source", "api"),
            "category": category,
            "priority": priority,
            "priority_level": priority_config["level"],
            "sla_deadline": sla_deadline,
            "metadata": {
                "alert_id": alert_data.get("alert_id"),
                "host": alert_data.get("host"),
                "metric": alert_data.get("metric"),
                "value": alert_data.get("value"),
                "threshold": alert_data.get("threshold"),
                "tags": alert_data.get("tags", []),
                "severity": alert_data.get("severity"),
            },
        }

        if not is_needed:
            # Create a suppressed incident in the database
            incident_data["status"] = "suppressed"
            await create_incident(incident_data)
            await update_incident(
                incident_id,
                {
                    "status": "suppressed",
                    "root_cause": f"Bypassed: Non-ticketing alert. Reason: {reason}",
                    "resolution": f"Log anomaly monitored. No ticket created in ITSM.",
                },
            )
            await add_timeline_entry(
                incident_id,
                "agent-01",
                "Ticket Creator Agent",
                "suppressed",
                f"Suppressed alert from environment '{host}'. Reason: {reason}. Ticket creation bypassed.",
            )
            self.logger.info(
                f"Alert suppressed. No ticket created for non-prod host {host}"
            )
            return None

        await create_incident(incident_data)

        # Create in real BMC Helix
        from bmc_helix_connector import bmc_helix

        bmc_inc_number = await bmc_helix.create_incident(
            title=incident_data["title"],
            description=f"Category: {category}\nHost: {alert_data.get('host')}\n\n{incident_data['description']}",
        )

        if bmc_inc_number:
            incident_data["metadata"]["bmc_helix_inc"] = bmc_inc_number
            await update_incident(
                incident_id,
                {
                    "metadata": json.dumps(incident_data["metadata"]),
                    "status": "triaged",
                    "assigned_agent": "agent-01",
                },
            )
            await self.log_action(
                incident_id,
                "ticket_created",
                f"Created local ticket {incident_id} AND enterprise BMC Helix Incident {bmc_inc_number}",
            )
        else:
            await update_incident(
                incident_id, {"status": "triaged", "assigned_agent": "agent-01"}
            )
            await self.log_action(
                incident_id,
                "ticket_created",
                f"Created local ticket {incident_id} | Category: {category} | Priority: {priority.upper()} (P{priority_config['level']})",
            )

        await self.log_action(
            incident_id,
            "categorized",
            f"Auto-categorized as [{category}] based on keyword analysis",
        )
        await self.log_action(
            incident_id,
            "prioritized",
            f"Priority set to {priority.upper()} (P{priority_config['level']}) | Auto-escalate: {priority_config['auto_escalate']}",
        )

        self.logger.info(
            f"Ticket created: {incident_id} [{category}] P{priority_config['level']}"
        )
        return incident_id
