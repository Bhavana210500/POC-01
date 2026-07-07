import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseAgent(ABC):
    """Base class for all Helix AIOps agents."""

    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.logger = logging.getLogger(f"agent.{agent_id}")
        self.status = "idle"
        self.tasks_completed = 0

    @abstractmethod
    async def process(self, data) -> dict:
        """Process an incident. Must be implemented by subclasses."""
        pass

    async def log_action(self, incident_id: str, action: str, details: str):
        """Log an action to the incident timeline."""
        from database import add_timeline_entry

        await add_timeline_entry(incident_id, self.agent_id, self.name, action, details)
        self.logger.info(f"[{incident_id}] {action}: {details}")

    def get_timestamp(self):
        return datetime.now(timezone.utc).isoformat()
