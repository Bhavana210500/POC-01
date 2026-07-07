import json
import asyncio
from agents.base_agent import BaseAgent


class KnowledgeBaseAgent(BaseAgent):
    """Agent 3: Searches knowledge base for solutions."""

    def __init__(self):
        super().__init__("agent-03", "Knowledge Base Agent")

    def _extract_keywords(self, incident):
        """Extract search keywords from incident data."""
        text = f"{incident.get('title', '')} {incident.get('description', '')} {incident.get('root_cause', '')}".lower()
        metadata = json.loads(incident.get("metadata", "{}"))
        tags = metadata.get("tags", [])

        keywords = list(set(tags))

        # Extract key terms from text
        key_terms = [
            "cpu",
            "memory",
            "disk",
            "network",
            "database",
            "ssl",
            "certificate",
            "connection",
            "pool",
            "timeout",
            "crash",
            "oom",
            "leak",
            "security",
            "login",
            "ssh",
            "brute",
            "firewall",
            "latency",
            "replication",
            "pod",
            "kubernetes",
            "container",
            "restart",
            "log",
            "error",
        ]
        for term in key_terms:
            if term in text and term not in keywords:
                keywords.append(term)

        return keywords

    async def process(self, incident_id) -> dict:
        """Search knowledge base for matching solutions using the ML engine."""
        from database import get_incident, update_incident
        from ml_model import ml_model

        incident = await get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        await self.log_action(
            incident_id,
            "kb_search_started",
            "Searching historical closed incidents and runbooks using local NLP ML Model...",
        )

        await asyncio.sleep(1)

        # Find best match in ML engine
        match = ml_model.find_best_match(
            incident.get("title", ""), incident.get("description", "")
        )

        best_match = None
        confidence = 0.2
        recommended_action = (
            "No matched resolution found in history. Manual intervention required."
        )
        title = "None"
        script = "app_restart.py"

        if match:
            best_match = match["item"]
            confidence = match["score"]
            recommended_action = best_match.get("resolution") or "No resolution notes."
            title = best_match.get("title") or "Historical Case"
            script = best_match.get("script") or "app_restart.py"

            # Normalize confidence to fit standard bounds (max 0.98)
            confidence = min(max(confidence, 0.2), 0.98)

        await update_incident(
            incident_id,
            {"recommended_action": recommended_action, "confidence_score": confidence},
        )

        # Save matched script to metadata so the self-healing agent knows what to run!
        import json

        metadata = json.loads(incident.get("metadata", "{}"))
        metadata["recommended_script"] = script
        await update_incident(incident_id, {"metadata": json.dumps(metadata)})

        if best_match and confidence >= 0.7:
            await self.log_action(
                incident_id,
                "kb_match_found",
                f"[LOCAL NLP ENGINE] Found historical match: '{title}' | Cosine Similarity: {confidence:.0%}",
            )
            await self.log_action(
                incident_id,
                "kb_recommendation",
                f"Recommended resolution: {recommended_action}",
            )
            await self.log_action(
                incident_id,
                "kb_auto_approve",
                f"High similarity ({confidence:.0%}) >= 70% threshold. Routing to automated background self-healing...",
            )
            return {
                "incident_id": incident_id,
                "match_found": True,
                "solution": recommended_action,
                "confidence": confidence,
                "runbook_title": title,
                "script": script,
            }
        else:
            if best_match:
                await self.log_action(
                    incident_id,
                    "kb_low_confidence",
                    f"[LOCAL NLP ENGINE] Best match: '{title}' with low similarity ({confidence:.0%}). Manual triage required.",
                )
            else:
                await self.log_action(
                    incident_id,
                    "kb_no_match",
                    "No historical incidents matched the signature. Manual investigation required.",
                )

            await self.log_action(
                incident_id,
                "kb_manual_review",
                f"Similarity ({confidence:.0%}) < 70% threshold. Pausing pipeline at Approval Gateway for Operator instructions.",
            )
            return {
                "incident_id": incident_id,
                "match_found": False,
                "confidence": confidence,
            }
