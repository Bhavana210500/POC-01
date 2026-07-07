"""
Splunk Cloud Session Auth Tester
────────────────────────────────
Port 443 is reachable but returns HTTP 303 (redirect to login).
This script authenticates via the /services/auth/login endpoint
to get a session key, then uses it to run searches.

This is how the Splunk Web UI itself works internally.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

HOST = os.getenv("SPLUNK_HOST", "https://prd-p-mrttm.splunkcloud.com").rstrip("/")
USERNAME = os.getenv("SPLUNK_USERNAME", "sc_admin")
PASSWORD = os.getenv("SPLUNK_PASSWORD", "")
QUERY = os.getenv("SPLUNK_QUERY", "search index=main | head 5")

import httpx


def separator():
    print("-" * 70)


def try_session_auth(base_url, username, password):
    """
    Authenticate via Splunk's /services/auth/login endpoint.
    Returns session key on success, None on failure.
    """
    login_urls = [
        f"{base_url}/services/auth/login",
        f"{base_url}/en-US/splunkd/__raw/services/auth/login",
    ]

    for login_url in login_urls:
        print(f"  [Auth] Trying: {login_url}")
        try:
            resp = httpx.post(
                login_url,
                data={
                    "username": username,
                    "password": password,
                    "output_mode": "json",
                },
                verify=False,
                follow_redirects=False,
                timeout=10.0,
            )
            print(f"  [Auth] Response: HTTP {resp.status_code}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    session_key = data.get("sessionKey") or data.get(
                        "response", {}
                    ).get("sessionKey", "")
                    if session_key:
                        print(f"  [Auth] ✓ Got session key: {session_key[:20]}...")
                        return session_key
                except Exception:
                    pass

                # Try XML parsing (Splunk default)
                import re

                match = re.search(r"<sessionKey>(.*?)</sessionKey>", resp.text)
                if match:
                    session_key = match.group(1)
                    print(f"  [Auth] ✓ Got session key (XML): {session_key[:20]}...")
                    return session_key

                print(f"  [Auth] Response body: {resp.text[:200]}")

            elif resp.status_code in [301, 302, 303, 307]:
                location = resp.headers.get("location", "")
                print(f"  [Auth] Redirect to: {location}")
                # Follow redirect manually
                if location:
                    abs_url = (
                        location
                        if location.startswith("http")
                        else f"{base_url}{location}"
                    )
                    resp2 = httpx.post(
                        abs_url,
                        data={
                            "username": username,
                            "password": password,
                            "output_mode": "json",
                        },
                        verify=False,
                        follow_redirects=True,
                        timeout=10.0,
                    )
                    print(f"  [Auth] Redirect response: HTTP {resp2.status_code}")
                    if resp2.status_code == 200:
                        try:
                            data = resp2.json()
                            session_key = data.get("sessionKey", "")
                            if session_key:
                                print(
                                    f"  [Auth] ✓ Got session key: {session_key[:20]}..."
                                )
                                return session_key
                        except Exception:
                            pass
                        import re

                        match = re.search(r"<sessionKey>(.*?)</sessionKey>", resp2.text)
                        if match:
                            session_key = match.group(1)
                            print(
                                f"  [Auth] ✓ Got session key (XML): {session_key[:20]}..."
                            )
                            return session_key
                        print(f"  [Auth] Redirect body: {resp2.text[:200]}")
            else:
                print(f"  [Auth] Body: {resp.text[:200]}")

        except Exception as e:
            print(f"  [Auth] Error: {type(e).__name__}: {str(e)[:120]}")

    return None


def search_with_session(base_url, session_key, query):
    """Run a search using the session key."""
    search_urls = [
        f"{base_url}/services/search/jobs/export",
        f"{base_url}/en-US/splunkd/__raw/services/search/jobs/export",
        f"{base_url}/splunkd/__raw/services/search/jobs/export",
    ]

    headers = {"Authorization": f"Splunk {session_key}"}
    data = {
        "search": query if query.strip().startswith("search") else f"search {query}",
        "output_mode": "json",
        "earliest_time": "-5m",
        "latest_time": "now",
    }

    for search_url in search_urls:
        print(f"\n  [Search] Trying: {search_url}")
        try:
            resp = httpx.post(
                search_url,
                data=data,
                headers=headers,
                verify=False,
                follow_redirects=True,
                timeout=15.0,
            )
            print(
                f"  [Search] Response: HTTP {resp.status_code}, {len(resp.text)} bytes"
            )

            if resp.status_code == 200 and not resp.text.strip().lower().startswith(
                "<!doc"
            ):
                events = []
                for line in resp.text.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        event_data = json.loads(line)
                        result = event_data.get("result", {})
                        if result:
                            events.append(result)
                    except json.JSONDecodeError:
                        pass

                print(f"  [Search] ✓ Retrieved {len(events)} events!")
                for i, ev in enumerate(events[:5]):
                    raw = ev.get("_raw", str(ev))
                    print(f"    [{i+1}] {raw[:100]}")
                return events

            elif resp.status_code in [301, 302, 303]:
                loc = resp.headers.get("location", "")
                print(f"  [Search] Redirect to: {loc}")
            else:
                print(f"  [Search] Body: {resp.text[:200]}")

        except Exception as e:
            print(f"  [Search] Error: {type(e).__name__}: {str(e)[:120]}")

    return None


def try_splunkd_proxy(base_url, username, password, query):
    """
    Try the Splunk Web proxy-to-splunkd approach.
    The Web UI proxies API calls via /en-US/splunkd/__raw/ on port 443.
    We authenticate via cookie-based session first.
    """
    print("\n[Method] Cookie-based Web UI session + splunkd proxy")
    separator()

    client = httpx.Client(verify=False, follow_redirects=True, timeout=15.0)

    # Step 1: Get the login page to obtain cval/csrf token
    print("  [Step 1] Fetching login page for CSRF token...")
    try:
        login_page = client.get(f"{base_url}/en-US/account/login")
        print(f"  Response: HTTP {login_page.status_code}")

        import re

        cval_match = re.search(r'"cval"\s*:\s*"(\d+)"', login_page.text)
        cval = cval_match.group(1) if cval_match else ""
        print(f"  CSRF cval: {cval or '(not found)'}")
    except Exception as e:
        print(f"  Error: {e}")
        return None

    # Step 2: POST login credentials
    print(f"\n  [Step 2] Posting login credentials (user: {username})...")
    try:
        login_data = {
            "username": username,
            "password": password,
            "cval": cval,
            "set_has_logged_in": "false",
        }
        login_resp = client.post(
            f"{base_url}/en-US/account/login",
            data=login_data,
        )
        print(f"  Response: HTTP {login_resp.status_code}")

        cookies = dict(client.cookies)
        has_session = any(
            "session" in k.lower() or "splunkd" in k.lower() or "token" in k.lower()
            for k in cookies
        )
        print(f"  Cookies: {list(cookies.keys())}")
        print(f"  Has session cookie: {has_session}")

        if not cookies:
            print(f"  Body: {login_resp.text[:300]}")
    except Exception as e:
        print(f"  Error: {e}")
        return None

    # Step 3: Use the session to call the search API via splunkd proxy
    print(f"\n  [Step 3] Running search via splunkd proxy...")
    search_endpoints = [
        f"{base_url}/en-US/splunkd/__raw/services/search/jobs/export",
        f"{base_url}/services/search/v2/jobs/export",
        f"{base_url}/en-US/api/search/jobs/export",
    ]

    for endpoint in search_endpoints:
        try:
            search_data = {
                "search": (
                    query if query.strip().startswith("search") else f"search {query}"
                ),
                "output_mode": "json",
                "earliest_time": "-5m",
                "latest_time": "now",
            }
            resp = client.post(endpoint, data=search_data)
            print(
                f"  [{endpoint.split('/')[-1]}] HTTP {resp.status_code}, {len(resp.text)} bytes"
            )

            if resp.status_code == 200 and not resp.text.strip().lower().startswith(
                "<!doc"
            ):
                events = []
                for line in resp.text.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        event_data = json.loads(line)
                        result = event_data.get("result", {})
                        if result:
                            events.append(result)
                    except json.JSONDecodeError:
                        pass

                print(f"\n  ✓ SUCCESS! Retrieved {len(events)} events!")
                for i, ev in enumerate(events[:5]):
                    raw = ev.get("_raw", str(ev))
                    print(f"    [{i+1}] {raw[:100]}")
                client.close()
                return events
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {str(e)[:120]}")

    client.close()
    return None


if __name__ == "__main__":
    print("=" * 70)
    print("  SPLUNK SESSION AUTH TESTER")
    print("=" * 70)
    print(f"  Host:     {HOST}")
    print(f"  Username: {USERNAME}")
    print(f"  Password: {'*' * len(PASSWORD)}")
    separator()

    # Method 1: Direct /services/auth/login
    print("\n[Method 1] Direct auth/login endpoint")
    separator()

    base_urls = [
        HOST,
        HOST.replace("prd-p-mrttm", "api-prd-p-mrttm"),  # API subdomain variant
    ]

    session_key = None
    for base in base_urls:
        print(f"\n  Base URL: {base}")
        session_key = try_session_auth(base, USERNAME, PASSWORD)
        if session_key:
            break

    if session_key:
        print(f"\n✓ Session key obtained! Running search...")
        separator()
        for base in base_urls:
            results = search_with_session(base, session_key, QUERY)
            if results:
                print(f"\n✅ SUCCESS! Fetched {len(results)} events from Splunk!")
                break
    else:
        print("\n  Session key auth failed. Trying cookie-based approach...")

    # Method 2: Cookie-based Web UI session
    separator()
    results = try_splunkd_proxy(HOST, USERNAME, PASSWORD, QUERY)

    if results:
        print(f"\n{'=' * 70}")
        print(f"  ✅ SUCCESS! The cookie-based Web UI session approach works!")
        print(f"  Retrieved {len(results)} events from Splunk Cloud.")
        print(f"  I will integrate this into the main pull scheduler.")
        print(f"{'=' * 70}")
    else:
        print(f"\n{'=' * 70}")
        print(f"  ❌ All session-based methods failed.")
        print(f"  The corporate proxy may be modifying requests.")
        print(f"  The app will continue in demo mode using testfile.log")
        print(f"{'=' * 70}")
