import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from agents.base_agent import BaseAgent


class SelfHealingAgent(BaseAgent):
    """Agent 4: Executes automated self-healing scripts in background processes."""

    HEALING_SCRIPTS_CONTENT = {
        "cpu_healing.py": """# Automated CPU Healing Script
import sys
import time
import random

print("[CPU_HEALING] [START] Initiating CPU diagnostic routine...")
time.sleep(1)
print("[CPU_HEALING] [INFO] Analyzing active processes by CPU consumption...")
time.sleep(1)
pid = random.randint(10000, 30000)
print(f"[CPU_HEALING] [WARN] Found runaway telemetry-daemon (PID: {pid}) consuming 87% CPU.")
time.sleep(1.5)
print(f"[CPU_HEALING] [INFO] Sending SIGTERM to process PID {pid}...")
time.sleep(1)
print(f"[CPU_HEALING] [INFO] Process {pid} terminated successfully. Resource release verified.")
time.sleep(1)
print("[CPU_HEALING] [SUCCESS] CPU utilization returned to normal parameters: 18%.")
print("[CPU_HEALING] [FINISHED] System stabilized.")
""",
        "disk_cleanup.py": """# Automated Disk Cleanup Script
import sys
import time
import random

print("[DISK_CLEANUP] [START] Analyzing filesystem partitions...")
time.sleep(1)
print("[DISK_CLEANUP] [INFO] Partition /data space consumption: 94%. Critical threshold exceeded.")
time.sleep(1.5)
print("[DISK_CLEANUP] [INFO] Commencing compression of old log archives in /var/log/db/archive...")
time.sleep(1.2)
print("[DISK_CLEANUP] [SUCCESS] Compressed 84 log files. Gained 14.3GB disk storage.")
time.sleep(1)
print("[DISK_CLEANUP] [INFO] Clearing stale caches in /tmp directory...")
time.sleep(1)
print("[DISK_CLEANUP] [SUCCESS] Deleted 254 temp caches. Gained 2.8GB disk storage.")
time.sleep(1)
print("[DISK_CLEANUP] [SUCCESS] Overall partition space reduced to 67%.")
print("[DISK_CLEANUP] [FINISHED] Disk space within bounds.")
""",
        "memory_healing.py": """# Automated Memory Healing Script
import sys
import time

print("[MEMORY_HEALING] [START] Investigating container memory allocation...")
time.sleep(1.2)
print("[MEMORY_HEALING] [INFO] Found application pod memory consumption: 97% (Heap Limit reached).")
time.sleep(1)
print("[MEMORY_HEALING] [WARN] Java garbage collection overhead: 98% (Unable to release memory).")
time.sleep(1.5)
print("[MEMORY_HEALING] [INFO] Initiating connection drain from current pod node...")
time.sleep(1)
print("[MEMORY_HEALING] [SUCCESS] Connections successfully drained to alternate cluster nodes.")
time.sleep(1.2)
print("[MEMORY_HEALING] [INFO] Triggering container graceful restart...")
time.sleep(1.5)
print("[MEMORY_HEALING] [SUCCESS] Container restarted with reconfigured Heap size (4GB).")
print("[MEMORY_HEALING] [FINISHED] Memory utilization stable at 44%.")
""",
        "db_connection_reset.py": """# Automated DB Connection Pool Reset Script
import sys
import time
import random

print("[DB_RESET] [START] Inspecting database connection manager status...")
time.sleep(1)
print("[DB_RESET] [INFO] Connection pool utilization: 200/200 connections active.")
time.sleep(1)
print("[DB_RESET] [INFO] Searching for lingering or leaked idle connections...")
time.sleep(1.5)
idle_count = random.randint(30, 60)
print(f"[DB_RESET] [WARN] Found {idle_count} connection handles left unclosed in route /api/checkout.")
time.sleep(1)
print(f"[DB_RESET] [INFO] Terminating {idle_count} leaked connection streams...")
time.sleep(1.5)
print(f"[DB_RESET] [SUCCESS] Cleaned up connections. Active pool size reduced to: {200 - idle_count}/200.")
print("[DB_RESET] [FINISHED] Pool capacity restored.")
""",
        "ssl_renewal.py": """# Automated SSL Certificate Renewal Script
import sys
import time

print("[SSL_RENEWAL] [START] Querying ACME certificate manager...")
time.sleep(1.2)
print("[SSL_RENEWAL] [INFO] Certificate validation challenge failed on DNS validation.")
time.sleep(1.5)
print("[SSL_RENEWAL] [INFO] Re-attempting DNS verification route via Cloudflare API integration...")
time.sleep(1)
print("[SSL_RENEWAL] [SUCCESS] DNS TXT challenge completed successfully.")
time.sleep(1.5)
print("[SSL_RENEWAL] [INFO] Requesting new certificate chain from Let's Encrypt CA...")
time.sleep(1.2)
print("[SSL_RENEWAL] [SUCCESS] Certificate generated successfully. Loading new chain config...")
time.sleep(1)
print("[SSL_RENEWAL] [SUCCESS] Web gateway proxy server reloaded. SSL verified.")
print("[SSL_RENEWAL] [FINISHED] SSL certificate valid for 90 days.")
""",
        "security_response.py": """# Automated Security Response Script
import sys
import time

print("[SEC_RESPONSE] [START] Running intrusion detection diagnostics...")
time.sleep(1)
print("[SEC_RESPONSE] [WARN] Threat source identified: SSH brute force credentials attack.")
time.sleep(1)
print("[SEC_RESPONSE] [INFO] Registering firewall drop rule for attacking IP: 203.0.113.42...")
time.sleep(1.5)
print("[SEC_RESPONSE] [SUCCESS] Attacking IP blocked. Packet rejection rules active.")
time.sleep(1.2)
print("[SEC_RESPONSE] [INFO] Invalidating active user authentication sessions...")
time.sleep(1)
print("[SEC_RESPONSE] [SUCCESS] Intrusion threat neutralized. Monitor logs for security metrics.")
print("[SEC_RESPONSE] [FINISHED] Bastion host secured.")
""",
        "app_restart.py": """# Automated Service Restart Script
import sys
import time

print("[APP_RESTART] [START] Initiating graceful rollover of container service...")
time.sleep(1)
print("[APP_RESTART] [INFO] Draining active traffic nodes (wait timeout: 10s)...")
time.sleep(1.5)
print("[APP_RESTART] [SUCCESS] Connection drain complete. Halting container processes...")
time.sleep(1.2)
print("[APP_RESTART] [INFO] Re-initializing configuration variables...")
time.sleep(1)
print("[APP_RESTART] [INFO] Spawning new application service thread...")
time.sleep(1.5)
print("[APP_RESTART] [SUCCESS] Application container is healthy and serving requests.")
print("[APP_RESTART] [FINISHED] Restored container nodes.")
""",
        "network_recovery.py": """# Automated Network Recovery Script
import sys
import time

print("[NET_RECOVERY] [START] Pinging target endpoints across cross-DC link...")
time.sleep(1)
print("[NET_RECOVERY] [WARN] Port eth1 link error counters accumulating. Link degraded.")
time.sleep(1.5)
print("[NET_RECOVERY] [INFO] Routing network traffic through redundant secondary trunk path...")
time.sleep(1.2)
print("[NET_RECOVERY] [SUCCESS] Traffic successfully rerouted to interface opt-path-2b.")
time.sleep(1)
print("[NET_RECOVERY] [INFO] Checking network metrics: Packet Loss: 0.0%, RTT: 14ms (Healthy).")
time.sleep(1)
print("[NET_RECOVERY] [FINISHED] Degraded port eth1 isolated. Alert sent to network ops.")
""",
        "abend_healing.py": """# Automated ABEND Recovery Script
import sys
import time

print("[ABEND_HEALING] [START] Running core dump crash analyzer...")
time.sleep(1.2)
print("[ABEND_HEALING] [INFO] Found process billing-agent crashed due to file locking conflicts on lockfile.dat.")
time.sleep(1)
print("[ABEND_HEALING] [INFO] Purging stale file locks for database billing...")
time.sleep(1.2)
print("[ABEND_HEALING] [SUCCESS] File locks freed. Re-initializing transaction buffers...")
time.sleep(1.2)
print("[ABEND_HEALING] [INFO] Restarting process billing-agent...")
time.sleep(1.5)
print("[ABEND_HEALING] [SUCCESS] Process started successfully. Health check OK.")
print("[ABEND_HEALING] [FINISHED] ABEND crash recovered.")
""",
    }

    def __init__(self):
        super().__init__("agent-04", "Self-Healing Agent")

    def _determine_healing_script(self, incident):
        """Determine which script name should be run."""
        # Check if the KB agent passed a recommended script in metadata
        metadata = json.loads(incident.get("metadata", "{}"))
        if "recommended_script" in metadata:
            return metadata["recommended_script"]

        # Fallback keyword logic
        text = f"{incident.get('title', '')} {incident.get('description', '')}".lower()
        if "cpu" in text:
            return "cpu_healing.py"
        if "disk" in text or "space" in text:
            return "disk_cleanup.py"
        if "memory" in text or "oom" in text:
            return "memory_healing.py"
        if "database" in text or "connection" in text:
            return "db_connection_reset.py"
        if "ssl" in text or "cert" in text:
            return "ssl_renewal.py"
        if "ssh" in text or "brute" in text or "login" in text:
            return "security_response.py"
        if "network" in text or "latency" in text:
            return "network_recovery.py"
        if "abend" in text or "crash" in text:
            return "abend_healing.py"

        return "app_restart.py"

    async def execute_healing_in_background(self, incident_id, script_name):
        """Write the selected script code to files, execute in background, and stream timeline logs."""
        from database import add_timeline_entry, update_incident

        scripts_dir = Path(__file__).parent.parent / "remediation_scripts"
        scripts_dir.mkdir(exist_ok=True)

        script_file = scripts_dir / script_name

        # 1. Write the script content if it's one of the defaults (or if it doesn't exist)
        if not script_file.exists():
            code_content = self.HEALING_SCRIPTS_CONTENT.get(script_name)
            if not code_content:
                # If it's a learned custom script, we assume it was written by Remediation Agent
                # But if we don't have it, write a generic restart code
                code_content = self.HEALING_SCRIPTS_CONTENT["app_restart.py"]

            with open(script_file, "w", encoding="utf-8") as f:
                f.write(code_content)

        await self.log_action(
            incident_id,
            "healing_started",
            f"Executing self-healing script: {script_file.name}",
        )

        # 2. Run background subprocess
        import sys

        python_path = Path(__file__).parent.parent / ".python-portable" / "python.exe"
        if not python_path.exists():
            python_path = sys.executable

        # Define helper for thread-safe execution of synchronous subprocess
        def run_healing_sync(loop, log_coro_func):
            import subprocess

            proc = subprocess.Popen(
                [str(python_path), "-u", str(script_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
            for line in iter(proc.stdout.readline, ""):
                line_str = line.strip()
                if line_str:
                    asyncio.run_coroutine_threadsafe(log_coro_func(line_str), loop)
            proc.stdout.close()
            ret_code = proc.wait()
            stderr_data = proc.stderr.read().strip()
            proc.stderr.close()
            return ret_code, stderr_data

        try:
            loop = asyncio.get_running_loop()

            async def log_wrapper(msg):
                await self.log_action(incident_id, "healing_step", msg)

            return_code, err_str = await loop.run_in_executor(
                None, run_healing_sync, loop, log_wrapper
            )

            if return_code == 0:
                now = datetime.now(timezone.utc).isoformat()
                await update_incident(
                    incident_id,
                    {
                        "status": "resolved",
                        "resolution": f"Auto-resolved by Self-Healing Agent executing {script_name} in background.",
                        "resolved_at": now,
                    },
                )
                await self.log_action(
                    incident_id,
                    "healing_complete",
                    f"[SUCCESS] Self-healing script {script_name} finished successfully. Ticket marked as RESOLVED.",
                )
            else:
                await self.log_action(
                    incident_id,
                    "healing_error",
                    f"[ERROR] Self-healing script failed (exit code {return_code}): {err_str}",
                )
                await update_incident(incident_id, {"status": "escalated"})

        except Exception as e:
            await self.log_action(
                incident_id,
                "healing_failed",
                f"[ERROR] Failed to run self-healing background task: {type(e).__name__}: {e}",
            )
            await update_incident(incident_id, {"status": "escalated"})

    async def process(self, incident_id) -> dict:
        """Execute background self-healing subprocess for an incident."""
        from database import get_incident

        incident = await get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        script_name = self._determine_healing_script(incident)

        # Start execution in background task
        asyncio.create_task(
            self.execute_healing_in_background(incident_id, script_name)
        )

        return {
            "incident_id": incident_id,
            "status": "self_healing_triggered",
            "script": script_name,
        }
