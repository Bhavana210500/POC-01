import random
import uuid
from datetime import datetime, timezone

ALERT_TEMPLATES = [
    {
        "title": "High CPU Usage on prod-web-server-01",
        "description": "CPU usage has exceeded 95% for the last 10 minutes on production web server. Multiple processes consuming excessive resources. Application response times degrading.",
        "source": "monitoring",
        "severity": "critical",
        "host": "prod-web-server-01",
        "metric": "cpu_usage",
        "value": 97.3,
        "threshold": 90,
        "tags": ["cpu", "performance", "production"],
    },
    {
        "title": "Disk Space Critical on db-server-03",
        "description": "Disk space on /data partition has reached 94%. Database logs are growing rapidly. Risk of database crash if disk fills completely.",
        "source": "monitoring",
        "severity": "high",
        "host": "db-server-03",
        "metric": "disk_usage",
        "value": 94,
        "threshold": 85,
        "tags": ["disk", "storage", "database"],
    },
    {
        "title": "Memory Leak Detected in payment-service",
        "description": "Memory consumption of payment-service has been steadily increasing. Current usage at 87% of allocated memory. Garbage collection unable to reclaim memory.",
        "source": "apm",
        "severity": "high",
        "host": "k8s-payment-pod-7d4f",
        "metric": "memory_usage",
        "value": 87,
        "threshold": 80,
        "tags": ["memory", "leak", "application", "payment"],
    },
    {
        "title": "Database Connection Pool Exhausted",
        "description": "All 200 database connections in the pool are in use. New requests are being queued. Average wait time has increased to 15 seconds.",
        "source": "application",
        "severity": "critical",
        "host": "app-server-cluster",
        "metric": "db_connections",
        "value": 200,
        "threshold": 180,
        "tags": ["database", "connection", "pool", "timeout"],
    },
    {
        "title": "SSL Certificate Expiring in 7 Days",
        "description": "SSL certificate for api.example.com will expire on 2026-06-18. Automated renewal has not triggered. Manual intervention may be required.",
        "source": "security_scanner",
        "severity": "medium",
        "host": "api.example.com",
        "metric": "cert_days_remaining",
        "value": 7,
        "threshold": 30,
        "tags": ["ssl", "certificate", "security", "expiry"],
    },
    {
        "title": "Multiple Failed SSH Login Attempts",
        "description": "Detected 847 failed SSH login attempts from IP 203.0.113.42 in the last hour. Possible brute force attack targeting production bastion host.",
        "source": "siem",
        "severity": "high",
        "host": "bastion-01",
        "metric": "failed_logins",
        "value": 847,
        "threshold": 50,
        "tags": ["security", "ssh", "brute_force", "login"],
    },
    {
        "title": "API Response Time Degradation",
        "description": "Average API response time has increased from 120ms to 2.3s over the last 30 minutes. Affecting /api/v2/orders and /api/v2/checkout endpoints.",
        "source": "apm",
        "severity": "high",
        "host": "api-gateway",
        "metric": "response_time_ms",
        "value": 2300,
        "threshold": 500,
        "tags": ["api", "latency", "performance", "degradation"],
    },
    {
        "title": "Kubernetes Pod CrashLoopBackOff",
        "description": "Pod order-service-5c8f7d in namespace production is in CrashLoopBackOff state. Last 5 restarts within 10 minutes. Exit code 137 (OOMKilled).",
        "source": "kubernetes",
        "severity": "critical",
        "host": "k8s-prod-cluster",
        "metric": "pod_restarts",
        "value": 5,
        "threshold": 3,
        "tags": ["kubernetes", "pod", "crash", "oom", "memory"],
    },
    {
        "title": "Network Latency Spike Between Data Centers",
        "description": "Network latency between DC-East and DC-West has spiked to 250ms (normally 15ms). Packet loss at 3.2%. Affecting cross-DC database replication.",
        "source": "network_monitor",
        "severity": "critical",
        "host": "dc-east-router",
        "metric": "latency_ms",
        "value": 250,
        "threshold": 50,
        "tags": ["network", "latency", "datacenter", "replication"],
    },
    {
        "title": "Log Volume Anomaly Detected",
        "description": "Error log volume has increased 500% in the last 15 minutes for auth-service. Primarily NullPointerException errors in JWT validation module.",
        "source": "log_aggregator",
        "severity": "medium",
        "host": "auth-service-cluster",
        "metric": "error_rate",
        "value": 500,
        "threshold": 100,
        "tags": ["logs", "errors", "auth", "application"],
    },
]


def generate_alert(template_index=None):
    """Generate a single alert from templates."""
    if template_index is not None:
        template = ALERT_TEMPLATES[template_index % len(ALERT_TEMPLATES)]
    else:
        template = random.choice(ALERT_TEMPLATES)

    alert = {
        "alert_id": f"ALR-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **template,
    }
    return alert


def generate_batch(count=3):
    """Generate a batch of random alerts."""
    indices = random.sample(
        range(len(ALERT_TEMPLATES)), min(count, len(ALERT_TEMPLATES))
    )
    return [generate_alert(i) for i in indices]
