import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self):
        self.agents = {}
        self.incident_queue = asyncio.Queue()
        self.approval_queue = asyncio.Queue()
        self.running = False
        self._listeners = []

    def register_agent(self, agent_id, agent):
        self.agents[agent_id] = agent
        logger.info(f"Registered agent: {agent_id} - {agent.name}")

    def add_listener(self, callback):
        self._listeners.append(callback)

    async def notify_listeners(self, event_type, data):
        for cb in self._listeners:
            try:
                await cb(event_type, data)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    async def submit_incident(self, alert_data):
        await self.incident_queue.put(alert_data)
        logger.info(f"Incident queued: {alert_data.get('title', 'Unknown')}")

    async def process_approval(self, incident_id, approved, comment=""):
        await self.approval_queue.put(
            {
                "incident_id": incident_id,
                "approved": approved,
                "comment": comment,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def run_pipeline(self, alert_data):
        """Run a single incident through the full agent pipeline."""
        from database import (
            add_timeline_entry,
            update_incident,
            get_incident,
            update_agent_status,
            increment_agent_tasks,
        )

        incident_id = None
        try:
            # Stage 1: Ticket Creator
            agent1 = self.agents.get("agent-01")
            if agent1:
                await update_agent_status(
                    "agent-01", agent1.name, "processing", alert_data.get("title")
                )
                await self.notify_listeners(
                    "agent_active", {"agent": "agent-01", "stage": "ticket_creation"}
                )
                incident_id = await agent1.process(alert_data)
                await increment_agent_tasks("agent-01")
                await update_agent_status("agent-01", agent1.name, "idle")
                await self.notify_listeners(
                    "ticket_created", {"incident_id": incident_id}
                )
                await asyncio.sleep(1)  # Simulate processing time

            if not incident_id:
                return

            # Stage 2: Root Cause Investigation
            agent2 = self.agents.get("agent-02")
            if agent2:
                await update_agent_status(
                    "agent-02", agent2.name, "processing", incident_id
                )
                await update_incident(
                    incident_id,
                    {"status": "investigating", "assigned_agent": "agent-02"},
                )
                await self.notify_listeners(
                    "agent_active", {"agent": "agent-02", "stage": "investigation"}
                )
                investigation = await agent2.process(incident_id)
                await increment_agent_tasks("agent-02")
                await update_agent_status("agent-02", agent2.name, "idle")
                await self.notify_listeners(
                    "investigation_complete",
                    {"incident_id": incident_id, "result": investigation},
                )
                await asyncio.sleep(1)

            # Stage 3: Knowledge Base Search
            agent3 = self.agents.get("agent-03")
            if agent3:
                await update_agent_status(
                    "agent-03", agent3.name, "processing", incident_id
                )
                await update_incident(
                    incident_id, {"status": "diagnosed", "assigned_agent": "agent-03"}
                )
                await self.notify_listeners(
                    "agent_active", {"agent": "agent-03", "stage": "knowledge_search"}
                )
                kb_result = await agent3.process(incident_id)
                await increment_agent_tasks("agent-03")
                await update_agent_status("agent-03", agent3.name, "idle")
                await self.notify_listeners(
                    "kb_search_complete",
                    {"incident_id": incident_id, "result": kb_result},
                )
                await asyncio.sleep(0.5)

            # Stage 4: Approval Gateway
            incident = await get_incident(incident_id)
            confidence = incident.get("confidence_score", 0) if incident else 0

            if confidence >= 0.7:
                # High confidence - auto-approve for self-healing
                await add_timeline_entry(
                    incident_id,
                    "system",
                    "Approval Gateway",
                    "auto_approved",
                    f"Auto-approved: confidence score {confidence:.0%} >= 70% threshold",
                )
                await update_incident(
                    incident_id,
                    {"status": "auto_healing", "assigned_agent": "agent-04"},
                )
                await self.notify_listeners(
                    "auto_approved",
                    {"incident_id": incident_id, "confidence": confidence},
                )

                # Stage 5a: Self-Healing
                agent4 = self.agents.get("agent-04")
                if agent4:
                    await update_agent_status(
                        "agent-04", agent4.name, "processing", incident_id
                    )
                    await self.notify_listeners(
                        "agent_active", {"agent": "agent-04", "stage": "self_healing"}
                    )
                    result = await agent4.process(incident_id)
                    await increment_agent_tasks("agent-04")
                    await update_agent_status("agent-04", agent4.name, "idle")
                    await self.notify_listeners(
                        "healing_complete",
                        {"incident_id": incident_id, "result": result},
                    )
            else:
                # Low confidence - require manual approval
                await add_timeline_entry(
                    incident_id,
                    "system",
                    "Approval Gateway",
                    "pending_approval",
                    f"Manual approval required: confidence score {confidence:.0%} < 70% threshold",
                )
                await update_incident(
                    incident_id,
                    {"status": "awaiting_approval", "assigned_agent": "agent-05"},
                )
                await self.notify_listeners(
                    "awaiting_approval",
                    {"incident_id": incident_id, "confidence": confidence},
                )

        except Exception as e:
            logger.error(f"Pipeline error for incident {incident_id}: {e}")
            if incident_id:
                await add_timeline_entry(
                    incident_id, "system", "Orchestrator", "error", str(e)
                )
                await update_incident(incident_id, {"status": "escalated"})
                await self.notify_listeners(
                    "pipeline_error", {"incident_id": incident_id, "error": str(e)}
                )

    async def handle_approval_response(
        self,
        incident_id,
        approved,
        comment="",
        remediation_steps="",
        remediation_type="text",
    ):
        """Handle human approval/rejection."""
        from database import (
            add_timeline_entry,
            update_incident,
            update_agent_status,
            increment_agent_tasks,
        )

        if approved:
            await add_timeline_entry(
                incident_id,
                "human",
                "Human Operator",
                "approved",
                f"Manually approved. Comment: {comment}",
            )

            # Route to remediation agent
            agent5 = self.agents.get("agent-05")
            if agent5:
                await update_incident(
                    incident_id,
                    {"status": "manual_remediation", "assigned_agent": "agent-05"},
                )
                await update_agent_status(
                    "agent-05", agent5.name, "processing", incident_id
                )
                await self.notify_listeners(
                    "agent_active", {"agent": "agent-05", "stage": "remediation"}
                )
                result = await agent5.process_manual(
                    incident_id, remediation_steps, remediation_type
                )
                await increment_agent_tasks("agent-05")
                await update_agent_status("agent-05", agent5.name, "idle")
                await self.notify_listeners(
                    "remediation_complete",
                    {"incident_id": incident_id, "result": result},
                )
        else:
            await add_timeline_entry(
                incident_id,
                "human",
                "Human Operator",
                "rejected",
                f"Rejected. Escalating. Comment: {comment}",
            )
            await update_incident(incident_id, {"status": "escalated"})
            await self.notify_listeners("escalated", {"incident_id": incident_id})

    async def start(self):
        """Start the orchestrator background loop."""
        self.running = True
        logger.info("Orchestrator started")
        while self.running:
            try:
                alert_data = await asyncio.wait_for(
                    self.incident_queue.get(), timeout=1.0
                )
                asyncio.create_task(self.run_pipeline(alert_data))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")

    async def stop(self):
        self.running = False
        logger.info("Orchestrator stopped")


# Global orchestrator instance
orchestrator = Orchestrator()
