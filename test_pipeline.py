#!/usr/bin/env python3
"""
Helix AIOps Platform - Backend Integration Test
This script verifies the full pipeline: alert ingestion, ML triage, root cause
investigation, KB matching, manual approval script generation, background execution,
and online active learning.
"""

import os
import httpx
import time
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

PORT = os.getenv("PORT", "8000")
BASE_URL = f"http://127.0.0.1:{PORT}"


def log(msg):
    print(f"[*] {msg}")


def check_server_status():
    log("Checking if FastAPI server is running...")
    try:
        res = httpx.get(f"{BASE_URL}/api/tickets")
        if res.status_code == 200:
            log("FastAPI server is running and accessible.")
            return True
    except Exception as e:
        log(f"FastAPI server is not accessible: {e}")
    return False


def wait_for_ticket_status(ticket_id, target_statuses, timeout=30):
    """Wait for a ticket to reach one of the target statuses."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        res = httpx.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        if res.status_code == 200:
            ticket = res.json().get("ticket", {})
            status = ticket.get("status")
            log(f"  Ticket {ticket_id} current status: {status}")
            if status in target_statuses:
                return res.json()
        time.sleep(2)
    raise TimeoutError(
        f"Ticket {ticket_id} did not reach {target_statuses} within {timeout} seconds."
    )


def run_tests():
    if not check_server_status():
        print(
            "[ERROR] Cannot run integration tests. Server is offline.", file=sys.stderr
        )
        sys.exit(1)

    client = httpx.Client()

    # Reset database to start with clean state
    log("Resetting database to a clean state...")
    res = client.post(f"{BASE_URL}/api/db/reset")
    if res.status_code == 200:
        log("Database reset successful.")
    else:
        log(f"Warning: database reset failed with status {res.status_code}")

    # =========================================================================
    # TEST 1: Simulate High-Confidence Auto-Healing Alert (CPU Alert)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 1: High-Confidence Auto-Healing Alert (CPU Alert)")
    print("=" * 80)

    # Simulate CPU Alert (Template 0)
    log("Triggering simulated CPU alert...")
    res = client.post(
        f"{BASE_URL}/api/simulate", json={"count": 1, "template_index": 0}
    )
    assert res.status_code == 200, "Simulation failed"
    simulated_alert = res.json()["alerts"][0]
    log(f"Triggered CPU alert: {simulated_alert['title']}")

    # Give orchestrator async queue time to process and create the ticket
    time.sleep(3)

    # Fetch latest tickets to get ticket_id
    res = client.get(f"{BASE_URL}/api/tickets")
    tickets = res.json().get("tickets", [])
    ticket = [t for t in tickets if t["title"] == simulated_alert["title"]][0]
    ticket_id = ticket["id"]
    log(
        f"Created ticket: {ticket_id} (Category: {ticket['category']}, Priority: {ticket['priority']})"
    )

    # Wait for the background process to resolve the ticket
    log("Waiting for automatic background self-healing subprocess...")
    detail = wait_for_ticket_status(ticket_id, ["resolved", "closed"])

    log("Verifying timeline entries for background execution...")
    timeline = detail.get("timeline", [])
    healing_steps = [
        e
        for e in timeline
        if e["action"] in ["healing_started", "healing_step", "healing_complete"]
    ]

    print("\nReal-time Timeline Execution Log:")
    for step in healing_steps:
        print(f"  [{step['agent_name']}] {step['details']}")
    print()

    assert len(healing_steps) > 0, "No healing logs found in timeline"
    log("TEST 1 PASSED: Alert successfully auto-healed in the background.")

    # =========================================================================
    # TEST 2: Low-Confidence Manual Intervention & NLP Script Parsing
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 2: Low-Confidence Manual Intervention & NLP Script Parsing")
    print("=" * 80)

    # Ingest a brand new custom alert with low similarity to current database
    custom_alert = {
        "search_name": "Custom Unfamiliar Alert Signature",
        "result": {
            "_raw": "2026-06-15 11:22:33 ERROR: Host print-svr-01 experienced print spooler service driver failure with backlog",
            "host": "print-svr-01",
            "source": "splunk_manual",
        },
    }
    log("Ingesting custom unfamiliar Splunk log alert...")
    res = client.post(f"{BASE_URL}/api/webhooks/splunk", json=custom_alert)
    assert res.status_code == 200

    # Give orchestrator async queue time to process and create the ticket
    time.sleep(3)

    # Fetch ticket
    res = client.get(f"{BASE_URL}/api/tickets")
    tickets = res.json().get("tickets", [])
    # Find ticket by host and timestamp or description
    ticket = [t for t in tickets if "print spooler" in t["description"]][0]
    custom_ticket_id = ticket["id"]
    log(f"Created ticket: {custom_ticket_id}")

    # Wait for it to pause at approval gateway
    log("Waiting for ticket to pause for Human Intervention...")
    detail = wait_for_ticket_status(custom_ticket_id, ["awaiting_approval"])
    assert detail["ticket"]["confidence_score"] < 0.7, "Confidence should be low"
    log(f"Paused successfully. Confidence: {detail['ticket']['confidence_score']:.1%}")

    # Provide manual resolution steps (text instructions)
    manual_steps = (
        "please restart postgres-database service and clear transaction log caches"
    )
    log(f"Submitting manual approval with resolution instructions: '{manual_steps}'")

    res = client.post(
        f"{BASE_URL}/api/tickets/{custom_ticket_id}/approve",
        json={
            "approved": True,
            "comment": "Triage instructions submitted by operator",
            "remediation_steps": manual_steps,
            "remediation_type": "text",
        },
    )
    assert res.status_code == 200
    log("Approval accepted. Spawning background script generator...")

    # Wait for background process to finish executing the dynamically generated script
    detail = wait_for_ticket_status(custom_ticket_id, ["resolved"])

    log("Verifying timeline entries for dynamic script execution...")
    timeline = detail.get("timeline", [])
    remediation_steps_log = [
        e
        for e in timeline
        if e["action"]
        in [
            "script_creation",
            "subprocess_log",
            "remediation_complete",
            "ml_online_training",
        ]
    ]

    print("\nDynamically Generated Remediation Console Log:")
    for step in remediation_steps_log:
        print(f"  [{step['agent_name']}] {step['details']}")
    print()

    # =========================================================================
    # TEST 3: Retraining & Auto-Healing Verification
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 3: Retraining Verification (Closed-Loop Learning)")
    print("=" * 80)

    log("Triggering the exact same unfamiliar Splunk log alert again...")
    res = client.post(f"{BASE_URL}/api/webhooks/splunk", json=custom_alert)
    assert res.status_code == 200

    # Give orchestrator async queue time to process and create the ticket
    time.sleep(3)

    # Fetch ticket
    res = client.get(f"{BASE_URL}/api/tickets")
    tickets = res.json().get("tickets", [])
    # Get the newest ticket matching description
    ticket = [
        t
        for t in tickets
        if "print spooler" in t["description"] and t["id"] != custom_ticket_id
    ][0]
    retrained_ticket_id = ticket["id"]
    log(f"Created second ticket: {retrained_ticket_id}")

    # Wait for it to resolve
    log(
        "Waiting for automatic self-healing (should auto-heal this time due to retraining)..."
    )
    detail = wait_for_ticket_status(retrained_ticket_id, ["resolved", "closed"])

    log(f"Verifying similarity score: {detail['ticket']['confidence_score']:.1%}")
    assert (
        detail["ticket"]["confidence_score"] >= 0.7
    ), "Retrained similarity should be >= 70%"

    timeline = detail.get("timeline", [])
    ml_logs = [
        e
        for e in timeline
        if "[LOCAL NLP ENGINE] Found historical match" in e["details"]
        or "healing_started" in e["action"]
    ]

    print("\nPipeline Logs for Retrained Ticket:")
    for step in ml_logs:
        print(f"  [{step['agent_name']}] {step['details']}")
    print()

    print("=" * 80)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
