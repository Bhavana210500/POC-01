import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

HELIX_API_URL = os.getenv("HELIX_API_URL", "https://mock-helix.local")
HELIX_USERNAME = os.getenv("HELIX_USERNAME", "mock_user")
HELIX_PASSWORD = os.getenv("HELIX_PASSWORD", "mock_pass")
HELIX_MOCK_MODE = os.getenv("HELIX_MOCK_MODE", "True").lower() == "true"

logger = logging.getLogger("bmc_helix")


class BMCHelixConnector:
    def __init__(self):
        self.base_url = HELIX_API_URL.rstrip("/")
        self.username = HELIX_USERNAME
        self.password = HELIX_PASSWORD
        self.token = None
        self.mock_mode = HELIX_MOCK_MODE

    async def login(self):
        if self.mock_mode:
            self.token = "mock-jwt-token"
            return True

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{self.base_url}/api/jwt/login",
                    data={"username": self.username, "password": self.password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                res.raise_for_status()
                self.token = res.text.strip()
                return True
        except Exception as e:
            logger.error(f"BMC Helix Login Failed: {e}")
            return False

    async def create_incident(
        self, title, description, impact="4-Minor/Localized", urgency="4-Low"
    ):
        if not self.token:
            await self.login()

        if self.mock_mode:
            logger.info(f"MOCK: Created BMC Helix Incident: {title}")
            import uuid

            return f"INC{str(uuid.uuid4().int)[:8]}"

        payload = {
            "values": {
                "First_Name": "System",
                "Last_Name": "Automation",
                "Description": title,
                "Detailed_Decription": description,
                "Impact": impact,
                "Urgency": urgency,
                "Status": "Assigned",
                "Reported Source": "Other",
                "Service_Type": "User Service Restoration",
            }
        }
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{self.base_url}/api/arsys/v1/entry/HPD:IncidentInterface_Create",
                    json=payload,
                    headers={
                        "Authorization": f"AR-JWT {self.token}",
                        "Content-Type": "application/json",
                    },
                )
                res.raise_for_status()
                return (
                    res.json().get("values", {}).get("Incident_Number", "UNKNOWN_INC")
                )
        except Exception as e:
            logger.error(f"Failed to create incident in BMC Helix: {e}")
            return None

    async def search_resolved_incidents(self, keywords):
        if not self.token:
            await self.login()

        if self.mock_mode:
            logger.info(f"MOCK: Searching BMC Helix for keywords: {keywords}")
            # Mock returning a past resolution
            if any(k in ["abend", "crash", "oom"] for k in keywords):
                return [
                    {
                        "Incident_Number": "INC00000012345",
                        "Description": "Job Abend Error",
                        "Resolution": "Restarted the batch job and cleared the tmp cache.",
                    }
                ]
            return []

        # Real BMC Helix Query: search Detailed Description for keywords, looking only at Closed/Resolved incidents
        query_str = "('Status' = \"Closed\" OR 'Status' = \"Resolved\")"
        if keywords:
            kw_conditions = " OR ".join(
                [f"'Detailed_Decription' LIKE \"%C{k}%\"" for k in keywords]
            )
            query_str += f" AND ({kw_conditions})"

        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{self.base_url}/api/arsys/v1/entry/HPD:IncidentInterface",
                    params={
                        "q": query_str,
                        "fields": "values(Incident_Number,Description,Resolution)",
                    },
                    headers={"Authorization": f"AR-JWT {self.token}"},
                )
                res.raise_for_status()
                return [
                    entry.get("values", {}) for entry in res.json().get("entries", [])
                ]
        except Exception as e:
            logger.error(f"Failed to search incidents in BMC Helix: {e}")
            return []


bmc_helix = BMCHelixConnector()
