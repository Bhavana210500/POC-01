import json
import asyncio
import random
from agents.base_agent import BaseAgent


class RootCauseInvestigator(BaseAgent):
    """Agent 2: Investigates root cause of incidents."""

    ROOT_CAUSE_PATTERNS = {
        "cpu": {
            "root_causes": [
                "Runaway process consuming excessive CPU cycles",
                "Insufficient CPU resources for current workload",
                "Crypto mining malware detected",
                "Infinite loop in application code",
            ],
            "investigation_steps": [
                "Checked top processes by CPU usage",
                "Analyzed CPU usage trends over last 24 hours",
                "Correlated with recent deployment events",
                "Reviewed application performance metrics",
            ],
        },
        "memory": {
            "root_causes": [
                "Memory leak in application heap",
                "Insufficient memory allocation for container",
                "Large dataset loaded into memory without streaming",
                "JVM garbage collection unable to free memory",
            ],
            "investigation_steps": [
                "Analyzed heap dump for memory leak patterns",
                "Reviewed memory usage trends",
                "Checked for recent code deployments",
                "Examined garbage collection logs",
            ],
        },
        "disk": {
            "root_causes": [
                "Log files growing without rotation",
                "Temporary files not cleaned up",
                "Database WAL files accumulating",
                "Large core dumps filling disk",
            ],
            "investigation_steps": [
                "Checked largest files and directories",
                "Reviewed log rotation configuration",
                "Analyzed disk growth rate",
                "Identified files modified in last 24 hours",
            ],
        },
        "database": {
            "root_causes": [
                "Connection pool exhausted due to connection leak",
                "Slow queries holding connections too long",
                "Database server under heavy load",
                "Network issues between app and database",
            ],
            "investigation_steps": [
                "Reviewed active database connections",
                "Analyzed slow query log",
                "Checked database server resource utilization",
                "Tested network connectivity to database",
            ],
        },
        "network": {
            "root_causes": [
                "Network congestion on inter-DC link",
                "Faulty network interface card",
                "BGP route flapping",
                "DDoS attack causing network saturation",
            ],
            "investigation_steps": [
                "Ran traceroute between affected endpoints",
                "Checked network interface error counters",
                "Reviewed BGP routing tables",
                "Analyzed traffic patterns for anomalies",
            ],
        },
        "security": {
            "root_causes": [
                "Brute force attack from external IP",
                "Compromised credentials being used",
                "SSL certificate auto-renewal failure",
                "Misconfigured firewall rules",
            ],
            "investigation_steps": [
                "Analyzed source IPs of failed login attempts",
                "Checked for compromised credentials in breach databases",
                "Reviewed SSL certificate chain and renewal logs",
                "Audited recent firewall rule changes",
            ],
        },
        "application": {
            "root_causes": [
                "Recent deployment introduced regression",
                "Dependency service is down or degraded",
                "Configuration change caused errors",
                "Resource limits reached in container",
            ],
            "investigation_steps": [
                "Reviewed recent deployment history",
                "Checked health of dependent services",
                "Compared configuration with last known good",
                "Analyzed application error logs",
            ],
        },
    }

    def __init__(self):
        super().__init__("agent-02", "Root Cause Investigator")

    def _determine_pattern(self, incident):
        """Match incident to a root cause pattern."""
        text = f"{incident.get('title', '')} {incident.get('description', '')} {incident.get('category', '')}".lower()
        metadata = json.loads(incident.get("metadata", "{}"))
        tags = metadata.get("tags", [])
        all_text = text + " " + " ".join(tags)

        for pattern_key in self.ROOT_CAUSE_PATTERNS:
            if pattern_key in all_text:
                return pattern_key

        return "application"  # default

    def _generate_dynamic_root_cause(self, pattern_key, incident):
        """Generate a realistic, randomized root cause incorporating incident metadata."""
        metadata = json.loads(incident.get("metadata", "{}"))
        host = metadata.get("host") or incident.get("host") or "unknown-host"
        val = metadata.get("value") or 1

        pid = random.randint(10000, 65000)

        if pattern_key == "cpu":
            proc = random.choice(
                [
                    "telemetry-agent",
                    "nginx-worker",
                    "node-runner",
                    "java-billing",
                    "query-engine",
                ]
            )
            return f"Runaway process '{proc}' (PID: {pid}) on host '{host}' consuming {val}% CPU due to thread lock condition."
        elif pattern_key == "memory":
            pod = f"k8s-{random.choice(['web', 'payment', 'order'])}-pod-{random.randint(1000, 9999):x}"
            return f"Memory leak in application heap space. Pod '{pod}' on host '{host}' has been terminated by Kubernetes kernel OOM killer (exit code 137)."
        elif pattern_key == "disk":
            path = random.choice(
                ["/var/log/nginx", "/tmp", "/data/db/journal", "/var/log/syslog"]
            )
            return f"Disk space partition full ({val}%). Stale temporary caches and uncompressed backup archives in directory '{path}' on host '{host}'."
        elif pattern_key == "database":
            route = random.choice(
                ["/api/v2/orders", "/api/v2/checkout", "/api/v1/user/auth"]
            )
            return f"Database connection pool exhausted. Active connection leak detected in API endpoint '{route}' on database host '{host}'. Pool utilization: {val}/200."
        elif pattern_key == "security":
            ip = f"{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
            if (
                "ssl" in incident.get("title", "").lower()
                or "certificate" in incident.get("title", "").lower()
            ):
                return f"SSL renewal script failed on host '{host}'. DNS validation challenge timed out under certificate authority request."
            return f"Bastion host '{host}' experienced {val} failed SSH password authentication attempts. Security alert: brute-force dictionary attack from IP address {ip}."
        elif pattern_key == "network":
            interface = random.choice(["eth0", "eth1", "trunk-link-1a", "opt-path-2b"])
            return f"Network packet loss ({val}%) detected on inter-DC interface '{interface}' on routing host '{host}' due to hardware port flapping."
        else:
            exception = random.choice(
                [
                    "NullPointerException",
                    "ConnectionResetError",
                    "IndexOutOfRangeError",
                    "JWTDecodeError",
                ]
            )
            return f"Fatal Exception '{exception}' raised in module checkout_gateway.py (line {random.randint(10, 500)}) on host '{host}'."

    async def process(self, incident_id) -> dict:
        """Investigate root cause of an incident."""
        from database import get_incident, update_incident

        incident = await get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        await self.log_action(
            incident_id, "investigation_started", "Beginning root cause analysis..."
        )

        # Simulate investigation time
        await asyncio.sleep(2)

        pattern_key = self._determine_pattern(incident)
        pattern = self.ROOT_CAUSE_PATTERNS[pattern_key]

        # Log investigation steps
        for step in pattern["investigation_steps"]:
            await self.log_action(incident_id, "investigation_step", f"✓ {step}")
            await asyncio.sleep(0.5)

        # Determine root cause dynamically
        from ml_model import MLModel

        model = MLModel()
        match = model.find_best_match(
            incident.get("title", ""), incident.get("description", "")
        )

        if match and match["score"] > 0.15:
            root_cause = match["item"]["root_cause"]
            await self.log_action(
                incident_id,
                "investigation_step",
                f"✓ ML Model root cause prediction (Confidence: {match['score']:.2f})",
            )
        else:
            root_cause = self._generate_dynamic_root_cause(pattern_key, incident)

        await update_incident(incident_id, {"root_cause": root_cause})
        await self.log_action(
            incident_id, "root_cause_identified", f"Root cause identified: {root_cause}"
        )

        result = {
            "incident_id": incident_id,
            "pattern": pattern_key,
            "root_cause": root_cause,
            "investigation_steps": pattern["investigation_steps"],
        }

        self.logger.info(f"Root cause for {incident_id}: {root_cause}")
        return result
