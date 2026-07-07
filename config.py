import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "helix.db"
KB_DIR = BASE_DIR / "knowledge_base"
STATIC_DIR = BASE_DIR / "static"

# Agent Configuration
AGENT_CONFIG = {
    "ticket_creator": {"name": "Ticket Creator", "id": "agent-01", "auto_assign": True},
    "root_cause": {
        "name": "Root Cause Investigator",
        "id": "agent-02",
        "max_correlations": 10,
    },
    "knowledge_base": {
        "name": "Knowledge Base Agent",
        "id": "agent-03",
        "confidence_threshold": 0.7,
    },
    "self_healing": {
        "name": "Self-Healing Agent",
        "id": "agent-04",
        "auto_execute": True,
    },
    "remediation": {
        "name": "Remediation Agent",
        "id": "agent-05",
        "require_approval": True,
    },
}

# Priority Levels
PRIORITY_MAP = {
    "critical": {"level": 1, "sla_minutes": 15, "auto_escalate": True},
    "high": {"level": 2, "sla_minutes": 60, "auto_escalate": True},
    "medium": {"level": 3, "sla_minutes": 240, "auto_escalate": False},
    "low": {"level": 4, "sla_minutes": 1440, "auto_escalate": False},
}

# Categories
CATEGORIES = [
    "Infrastructure",
    "Application",
    "Network",
    "Security",
    "Database",
    "Cloud",
]

# Workflow States
STATES = [
    "new",
    "triaged",
    "investigating",
    "diagnosed",
    "awaiting_approval",
    "auto_healing",
    "manual_remediation",
    "resolved",
    "closed",
    "escalated",
]
