"""
Quick Splunk Connection Tester
──────────────────────────────
Tests all possible connection methods to Splunk Cloud from your machine.
Run: python test_splunk_connection.py

This will try:
  1. SDK with username/password on port 8089
  2. SDK with username/password on port 443
  3. SDK with HEC token on port 8089
  4. SDK with HEC token on port 443
  5. REST API via httpx on port 443
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

HOST = (
    os.getenv("SPLUNK_HOST", "https://prd-p-mrttm.splunkcloud.com")
    .replace("https://", "")
    .replace("http://", "")
    .rstrip("/")
)
USERNAME = os.getenv("SPLUNK_USERNAME", "")
PASSWORD = os.getenv("SPLUNK_PASSWORD", "")
TOKEN = os.getenv("SPLUNK_TOKEN") or os.getenv("SPLUNK_HEC_TOKEN", "")
QUERY = os.getenv("SPLUNK_QUERY", "search index=main | head 5")


def separator():
    print("─" * 70)


def test_sdk(host, port, username=None, password=None, token=None):
    """Test Splunk SDK connection."""
    try:
        import splunklib.client as client
        import splunklib.results as results
    except ImportError:
        print("  ✗ splunklib not installed. Run: pip install splunk-sdk")
        return False

    connect_kwargs = {"host": host, "port": port, "scheme": "https"}

    if username and password:
        connect_kwargs["username"] = username
        connect_kwargs["password"] = password
        auth_desc = f"username/password ({username})"
    elif token:
        connect_kwargs["splunkToken"] = token
        auth_desc = f"token ({token[:12]}...)"
    else:
        print("  ✗ No credentials provided")
        return False

    print(f"  Trying SDK → {host}:{port} with {auth_desc} ...")
    try:
        service = client.connect(**connect_kwargs)
        # Test by listing apps (lightweight call)
        apps = [app.name for app in service.apps.list()[:3]]
        print(f"  ✓ SUCCESS! Connected. Apps: {apps}")

        # Try a quick search
        print(f"  Running search: {QUERY[:60]}...")
        job_results = service.jobs.oneshot(
            QUERY if QUERY.strip().startswith("search") else f"search {QUERY}",
            earliest_time="-5m",
            latest_time="now",
            output_mode="json",
            count=5,
        )
        count = 0
        for result in results.JSONResultsReader(job_results):
            if isinstance(result, dict):
                raw = result.get("_raw", str(result))
                print(f"    Event: {raw[:100]}")
                count += 1
        print(f"  ✓ Search returned {count} events")
        return True

    except Exception as e:
        err = str(e)
        if "401" in err or "Login failed" in err:
            print(
                f"  ✗ AUTH FAILED (port {port} is reachable, but credentials are wrong)"
            )
            print(f"    Error: {err[:150]}")
        elif "timed out" in err.lower() or "timeout" in err.lower():
            print(f"  ✗ TIMEOUT (port {port} blocked by firewall)")
        elif "Connection refused" in err:
            print(f"  ✗ CONNECTION REFUSED (port {port} not open)")
        else:
            print(f"  ✗ FAILED: {type(e).__name__}: {err[:150]}")
        return False


def test_rest(host, port=443):
    """Test REST API via httpx."""
    try:
        import httpx
    except ImportError:
        print("  ✗ httpx not installed")
        return False

    url = f"https://{host}:{port}/services/search/jobs/export"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    auth = (USERNAME, PASSWORD) if (USERNAME and PASSWORD) else None

    print(f"  Trying REST → {url} ...")
    try:
        data = {
            "search": (
                QUERY if QUERY.strip().startswith("search") else f"search {QUERY}"
            ),
            "output_mode": "json",
            "earliest_time": "-5m",
            "latest_time": "now",
        }
        resp = httpx.post(
            url, data=data, headers=headers, auth=auth, verify=False, timeout=5.0
        )
        if resp.status_code == 200:
            print(f"  ✓ SUCCESS! HTTP 200, {len(resp.text)} bytes")
            return True
        else:
            print(f"  ✗ HTTP {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {str(e)[:150]}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("  SPLUNK CONNECTION TESTER — Helix AIOps Platform")
    print("=" * 70)
    print(f"  Host:     {HOST}")
    print(f"  Username: {USERNAME or '(empty — set SPLUNK_USERNAME in .env)'}")
    print(
        f"  Password: {'*' * len(PASSWORD) if PASSWORD else '(empty — set SPLUNK_PASSWORD in .env)'}"
    )
    print(f"  Token:    {TOKEN[:16] + '...' if TOKEN else '(empty)'}")
    print(f"  Query:    {QUERY[:60]}")
    separator()

    if not USERNAME and not PASSWORD:
        print("\n⚠️  SPLUNK_USERNAME and SPLUNK_PASSWORD are empty in .env!")
        print(
            "   Enter your Splunk Web UI login credentials below, or set them in .env:\n"
        )
        USERNAME = input("   Splunk Username: ").strip()
        PASSWORD = input("   Splunk Password: ").strip()
        if not USERNAME or not PASSWORD:
            print("\n   No credentials entered. Will try token auth only.\n")
        separator()

    success = False

    # Test 1: SDK with username/password
    if USERNAME and PASSWORD:
        print("\n[Test 1] SDK + Username/Password + Port 8089")
        if test_sdk(HOST, 8089, username=USERNAME, password=PASSWORD):
            success = True
        separator()

        print("\n[Test 2] SDK + Username/Password + Port 443")
        if not success and test_sdk(HOST, 443, username=USERNAME, password=PASSWORD):
            success = True
        separator()

    # Test 2: SDK with token
    if TOKEN and not success:
        print("\n[Test 3] SDK + Token + Port 8089")
        if test_sdk(HOST, 8089, token=TOKEN):
            success = True
        separator()

        print("\n[Test 4] SDK + Token + Port 443")
        if not success and test_sdk(HOST, 443, token=TOKEN):
            success = True
        separator()

    # Test 3: REST API
    if not success:
        print("\n[Test 5] REST API (httpx) + Port 443")
        if test_rest(HOST, 443):
            success = True
        separator()

    print()
    if success:
        print("✅ At least one connection method works!")
        print(
            "   Update your .env file with the working credentials and restart main.py"
        )
    else:
        print("❌ All connection methods failed.")
        print("   Possible reasons:")
        print("   • Wrong username/password (can you log into the Splunk Web UI?)")
        print("   • Corporate firewall blocking all outbound Splunk ports")
        print("   • Token expired or invalid")
        print("\n   The app will continue working in demo mode using testfile.log")
    print()
