# Helix AIOps Platform POC

This project is a Proof of Concept (POC) demonstrating an automated AI Operations platform that pulls logs from Splunk, automatically correlates incidents, determines root causes, and manages remediation workflows via BMC Helix.

## Setup Instructions

### 1. Connect to Splunk

To pull live logs from Splunk, configure the following variables in your `.env` file located in the root of the project:

```env
# Splunk REST API URL (usually port 8089)
SPLUNK_API_URL=https://<your-splunk-tenant>.splunkcloud.com:8089

# Splunk Authentication (Use Token OR Username/Password)
SPLUNK_TOKEN=<your-jwt-or-hec-token>
SPLUNK_USERNAME=<your-splunk-username>
SPLUNK_PASSWORD=<your-splunk-password>

# The SPL search query used to pull error logs
SPLUNK_QUERY=search index=main (error OR fail OR fatal OR abend OR crash)

# How often to pull logs from Splunk (in seconds)
SPLUNK_POLL_INTERVAL=300
```
> **Note**: If you don't provide valid Splunk credentials, the application will fallback to **Mock Mode** and simulate live logs by monitoring `testfile.log`.

---

### 2. Connect to BMC Helix Dashboard

By default, the platform runs with a mock Helix connector. To connect it to your actual BMC Helix ITSM dashboard for creating tickets and querying historical resolutions, update your `.env` file with the following:

```env
# Disable mock mode to use the real Helix API
HELIX_MOCK_MODE=False

# Your BMC Helix API URL
HELIX_API_URL=https://<your-helix-tenant>-restapi.onbmc.com

# Authentication credentials for the API user
HELIX_USERNAME=<your-api-user>
HELIX_PASSWORD=<your-api-password>
```

When mock mode is disabled, the system will use the `BMCHelixConnector` to authenticate via JWT and create incident tickets (`HPD:IncidentInterface_Create`) directly in your Helix environment.

---

### 3. Run the Application

Once your `.env` file is configured, launch the server:

```bash
python main.py
```

The application will start the agent orchestrator, begin polling Splunk in the background, and host the dashboard. You can access the UI by navigating to:
**http://localhost:8000**
