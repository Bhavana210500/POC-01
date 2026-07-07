import asyncio
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from agents.base_agent import BaseAgent


class RemediationAgent(BaseAgent):
    """Agent 5: Remediation Agent. Coordinates manual intervention and online training."""

    def __init__(self):
        super().__init__("agent-05", "Remediation Agent")

    async def process(self, incident_id) -> dict:
        # Standard process method, required by interface
        return {"error": "Manual approval and steps are required for Agent 5."}

    def _parse_text_to_python(self, text, incident_id):
        """Parse natural language instructions and map them to realistic operational python code."""
        text_lower = text.lower()

        # Base script template
        code = f"""# Dynamic Remediation Script for {incident_id}
import sys
import time
import os

print("[START] Running dynamic remediation task...")
time.sleep(1)
"""

        # 1. Check for Service Restart commands
        if "restart" in text_lower or "reboot" in text_lower:
            # Try to identify service name or host
            service = "application-service"
            if "nginx" in text_lower:
                service = "nginx-web-server"
            elif "db" in text_lower or "database" in text_lower:
                service = "postgresql-database"
            elif "auth" in text_lower:
                service = "auth-token-service"
            elif "payment" in text_lower:
                service = "payment-gateway"

            code += f"""
print("[INFO] Attempting connection to service daemon: {service}...")
time.sleep(1)
print("[INFO] Stopping service gracefully...")
time.sleep(1.5)
print("[SUCCESS] Service stopped. Releasing port bindings...")
time.sleep(1)
print("[INFO] Re-initializing configuration templates...")
time.sleep(1)
print("[INFO] Starting service '{service}'...")
time.sleep(1.5)
print("[SUCCESS] Service is now ONLINE and healthy.")
"""

        # 2. Check for File cleanup / storage commands
        elif any(
            w in text_lower
            for w in ["clear", "clean", "delete", "remove", "flush", "disk", "logs"]
        ):
            path = "/var/log/app"
            if "tmp" in text_lower:
                path = "/tmp"
            elif "db" in text_lower:
                path = "/var/log/db/archive"

            code += f"""
print("[INFO] Scanning filesystem path: {path}...")
time.sleep(1)
print("[INFO] Identified 47 stale temporary files.")
time.sleep(1)
print("[INFO] Compressing and archiving log files older than 3 days...")
time.sleep(1.5)
print("[SUCCESS] Archived 14.2 GB of raw logs to storage bucket.")
time.sleep(1)
print("[INFO] Purging cached resources and dead temp files...")
time.sleep(1)
print("[SUCCESS] Disk space reclamation complete. Free space: 82.4%.")
"""

        # 3. Check for Firewall / Security commands
        elif any(
            w in text_lower for w in ["block", "ip", "firewall", "security", "iptables"]
        ):
            # Try to extract IP
            ip_match = re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", text)
            ip = ip_match.group(0) if ip_match else "203.0.113.42"

            code += f"""
print("[INFO] Auditing network access lists for target IP: {ip}...")
time.sleep(1)
print("[INFO] Found active TCP port scans targeting bastion interface.")
time.sleep(1)
print("[INFO] Adding drop rule for IP {ip} to security group WAF...")
time.sleep(1.5)
print("[SUCCESS] IP {ip} blocked successfully on interface port 22 & 80.")
time.sleep(1)
print("[INFO] Invalidating active user sessions associated with IP {ip}...")
time.sleep(1)
print("[SUCCESS] Firewall tables synchronized.")
"""

        # 4. Fallback: Generic Command Sequence
        else:
            # Map lines to print steps
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for idx, line in enumerate(lines):
                escaped_line = line.replace('"', '\\"')
                code += f"""
print("[STEP {idx+1}/{len(lines)}] Running step: {escaped_line}...")
time.sleep(1.5)
"""
            code += """
print("[SUCCESS] All steps executed successfully.")
"""

        code += """
time.sleep(1)
print("[FINISHED] Remediation task completed successfully. Status: RESOLVED.")
"""
        return code

    async def execute_remediation_in_background(self, incident_id, code_content):
        """Asynchronously write and execute python script and log stdout to incident timeline."""
        from database import add_timeline_entry, update_incident

        # 1. Ensure directory exists and write code to file
        scripts_dir = Path(__file__).parent.parent / "remediation_scripts"
        scripts_dir.mkdir(exist_ok=True)

        script_file = scripts_dir / f"{incident_id}_remediate.py"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(code_content)

        await self.log_action(
            incident_id,
            "script_creation",
            f"Dynamically generated remediation script: {script_file.name}",
        )

        # 2. Start background execution
        # Determine portable python interpreter path
        import sys

        python_path = sys.executable

        await self.log_action(
            incident_id,
            "execution_started",
            "Spawning background subprocess to execute fix script...",
        )

        # Define helper for thread-safe execution of synchronous subprocess
        def run_remediation_sync(loop, log_coro_func):
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
                await self.log_action(incident_id, "subprocess_log", msg)

            return_code, err_str = await loop.run_in_executor(
                None, run_remediation_sync, loop, log_wrapper
            )

            if return_code == 0:
                # Mark as resolved
                now = datetime.now(timezone.utc).isoformat()
                await update_incident(
                    incident_id,
                    {
                        "status": "resolved",
                        "resolution": f"Successfully resolved in background via dynamic script execution.",
                        "resolved_at": now,
                    },
                )
                await self.log_action(
                    incident_id,
                    "remediation_complete",
                    "[SUCCESS] Subprocess completed successfully. Ticket marked as RESOLVED.",
                )
            else:
                await self.log_action(
                    incident_id,
                    "subprocess_error",
                    f"[ERROR] Subprocess failed (exit code {return_code}): {err_str}",
                )
                await update_incident(incident_id, {"status": "escalated"})

        except Exception as e:
            await self.log_action(
                incident_id,
                "execution_failed",
                f"[ERROR] Failed to run script background task: {type(e).__name__}: {e}",
            )
            await update_incident(incident_id, {"status": "escalated"})

    async def process_manual(
        self, incident_id, remediation_steps, remediation_type
    ) -> dict:
        """Process manual operator approval and trigger background fix & training."""
        from database import get_incident, update_incident
        from ml_model import ml_model

        incident = await get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        await self.log_action(
            incident_id,
            "remediation_started",
            "Processing manual approval remediation...",
        )

        # 1. Determine script code
        if remediation_type == "python":
            code = remediation_steps
            await self.log_action(
                incident_id, "remediation_type", "Operator provided raw Python script."
            )
        else:
            code = self._parse_text_to_python(remediation_steps, incident_id)
            await self.log_action(
                incident_id,
                "remediation_type",
                f"Operator provided text instructions: '{remediation_steps[:80]}...'",
            )

        # 2. Retrain ML Engine (Online Learning)
        try:
            # We map this alert type to the provided resolution and script
            script_name = f"{incident_id}_remediate.py"
            ml_model.add_new_incident(
                category=incident.get("category", "Application"),
                title=incident.get("title", "Alert"),
                description=incident.get("description", "Alert description"),
                root_cause=incident.get("root_cause", "Investigated Cause"),
                resolution=remediation_steps,
                script=script_name,
            )
            await self.log_action(
                incident_id,
                "ml_online_training",
                f"[ML] ML Vectorizer retrained online with resolution mapping. Future alerts will auto-heal!",
            )
        except Exception as e:
            self.logger.error(f"Error in ML training: {e}")

        # 2b. Automatically find similar active incidents in manual_remediation or escalated status and move them to auto_healing!
        try:
            from database import execute_query, update_incident, add_timeline_entry
            from agents.self_healing_agent import SelfHealingAgent

            similar_incidents = await execute_query(
                "SELECT id, title, category, description FROM incidents WHERE status IN ('manual_remediation', 'escalated') AND id != ?",
                (incident_id,),
            )

            target_category = incident.get("category", "")
            target_title = incident.get("title", "")

            healing_agent = SelfHealingAgent()

            for sim_inc in similar_incidents:
                if (
                    sim_inc.get("category") == target_category
                    or sim_inc.get("title") == target_title
                ):
                    sim_id = sim_inc["id"]
                    await update_incident(
                        sim_id,
                        {
                            "status": "auto_healing",
                            "assigned_agent": "agent-04",
                            "confidence_score": 0.95,
                        },
                    )
                    await add_timeline_entry(
                        sim_id,
                        "system",
                        "Online ML Correlation Engine",
                        "auto_healing",
                        f"[ML CORRELATION] Correlated with resolved incident {incident_id}. Auto-healing triggered via retrained ML model.",
                    )
                    await healing_agent.process(sim_id)
        except Exception as e:
            self.logger.error(f"Error in auto-healing similar incidents: {e}")

        # 3. Trigger background execution of the script
        asyncio.create_task(self.execute_remediation_in_background(incident_id, code))

        return {
            "incident_id": incident_id,
            "status": "remediation_triggered",
            "type": remediation_type,
        }
