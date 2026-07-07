#!/usr/bin/env python3
"""
Splunk Log Ingestion Simulator / Generator
This script sends log/alert events directly to a web endpoint over HTTP/HTTPS
without creating or writing to any local log files.

Supported Modes:
1. 'webhook' (Default): Sends events to the local Helix AIOps Splunk webhook
   (http://localhost:8000/api/webhooks/splunk) to trigger alert pipelines.
2. 'hec': Sends events to a real/external Splunk HTTP Event Collector (HEC) API.
3. 'file': (Optional) Appends logs to a local file.
"""

import argparse
import time
import random
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Realistic host names matching expected patterns
HOSTS = {
    "web": ["web-svr-01", "web-svr-02", "web-svr-03"],
    "db": ["db-server-01", "db-server-02", "db-server-03"],
    "api": ["api-service-01", "api-service-02"],
    "auth": ["auth-service-01"],
    "payment": ["payment-service-01"],
}

# Alerts designed to match the search signature keywords in the monitoring rules
ERROR_TEMPLATES = [
    (
        "error",
        "database connection failed - connection timed out after 30 seconds",
        "db",
    ),
    (
        "critical",
        "OutOfMemory (oom) crash occurred during transaction log checkpoint",
        "db",
    ),
    (
        "fatal",
        "application abend exception in main thread: stack overflow in billing module",
        "payment",
    ),
    ("error", "failed to authenticate token: signature validation failed", "auth"),
    ("error", "api response timeout while communicating with gateway-02", "api"),
    (
        "critical",
        "disk space critical: log directory partition full, database storage threatened",
        "db",
    ),
    (
        "error",
        "runtime exception: NullPointerException at order placement checkout flow",
        "web",
    ),
]


def generate_log_payload(level="error", host=None, custom_msg=None):
    """Generates an alert object with event data matching Splunk structure."""
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Select category and message template
    if level == "random":
        level = (
            "info"
            if random.random() > 0.3
            else random.choice(["error", "critical", "fatal"])
        )

    if custom_msg:
        h = host or "web-svr-01"
        msg_content = custom_msg
    else:
        category = "web"
        if level in ["error", "critical", "fatal"]:
            level, msg_content, category = random.choice(ERROR_TEMPLATES)
        else:
            msg_content = "processed request successfully"
            level = "info"
        h = host or random.choice(HOSTS[category])

    # Construct the raw log event text
    if level == "info":
        ip = f"192.168.1.{random.randint(10, 250)}"
        raw_event = f'{ip} - - [{now.strftime("%d/%b/%Y:%H:%M:%S +0000")}] "GET /api/v1/status HTTP/1.1" 200 452 "http://example.com" "Mozilla/5.0" host={h} level=INFO'
    else:
        # Match signatures like crash, oom, fatal
        if (
            level in ["critical", "fatal"]
            and "crash" not in msg_content.lower()
            and "oom" not in msg_content.lower()
        ):
            msg_content += " causing system crash and oom warning"
        raw_event = f'{timestamp_str} [{level.upper()}] host={h} event_id={random.randint(1000, 9999)} message="{msg_content}"'

    return {"host": h, "level": level, "raw_event": raw_event}


def send_http_request(url, payload, headers):
    """Sends a POST request to the specified web endpoint."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        # Bypass SSL certificate checks for local development/testing servers
        import ssl

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx) as response:
            res_body = response.read().decode("utf-8")
            print(f"[SUCCESS] Status: {response.status} | Response: {res_body}")
            return True
    except urllib.error.HTTPError as e:
        print(
            f"[ERROR] HTTP Error {e.code}: {e.read().decode('utf-8')}", file=sys.stderr
        )
        return False
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Splunk Web Log Ingestor. Inserts logs directly to web endpoints without writing local files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Insert an error alert to the local Helix Splunk Webhook (Default mode)
  python insert_splunk_logs.py --type error

  # Insert a critical memory crash alert to local Helix website/webhook
  python insert_splunk_logs.py --type critical --host db-server-01 --message "OOM exception database crash"

  # Send to an external Splunk HTTP Event Collector (HEC)
  python insert_splunk_logs.py --mode hec --url https://splunk-server:8088/services/collector --token "your-hec-token" --type critical
""",
    )

    parser.add_argument(
        "--mode",
        choices=["webhook", "hec", "file"],
        default="webhook",
        help="Target option: 'webhook' (Helix dashboard endpoint), 'hec' (Real Splunk HEC), or 'file' (log file).",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Target HTTP endpoint URL. If omitted, defaults are selected based on --mode.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Authorization token (required for Splunk HEC mode).",
    )
    parser.add_argument(
        "--type",
        choices=["info", "error", "critical", "fatal", "random"],
        default="random",
        help="Log/alert severity level to generate.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host name to set in the log event (e.g. web-svr-02, db-server-01).",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="A custom event message. If omitted, a realistic log entry is simulated.",
    )
    parser.add_argument(
        "--count", type=int, default=1, help="Number of log entries to insert."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds of delay between requests."
    )
    parser.add_argument(
        "--file-path",
        default="splunk_mock.log",
        help="Local file path (only used if --mode is 'file').",
    )

    args = parser.parse_args()

    # Set default URLs based on mode if not explicitly provided
    url = args.url
    if not url:
        if args.mode == "webhook":
            import os
            from pathlib import Path

            try:
                from dotenv import load_dotenv

                load_dotenv(Path(__file__).parent / ".env")
            except ImportError:
                pass
            port = os.getenv("PORT", "8000")
            url = f"http://localhost:{port}/api/webhooks/splunk"
        elif args.mode == "hec":
            url = "http://localhost:8088/services/collector"

    print(f"[START] Starting Splunk log generator in '{args.mode.upper()}' mode.")

    try:
        counter = 0
        for i in range(args.count):
            log_data = generate_log_payload(
                level=args.type, host=args.host, custom_msg=args.message
            )

            if args.mode == "webhook":
                # Construct payload for Helix Splunk Webhook
                payload = {
                    "search_name": f"Splunk Alert - {log_data['level'].upper()}",
                    "result": {
                        "_raw": log_data["raw_event"],
                        "host": log_data["host"],
                        "source": "splunk_web_generator",
                    },
                }
                headers = {"Content-Type": "application/json"}
                print(f"[SENDING] Posting Splunk webhook alert to {url}...")
                send_http_request(url, payload, headers)

            elif args.mode == "hec":
                # Construct payload for Splunk HEC
                payload = {
                    "time": time.time(),
                    "host": log_data["host"],
                    "source": "splunk_web_generator",
                    "sourcetype": "_json",
                    "index": "main",
                    "event": log_data["raw_event"],
                }
                headers = {
                    "Authorization": f"Splunk {args.token}",
                    "Content-Type": "application/json",
                }
                print(f"[SENDING] Posting to Splunk HEC API at {url}...")
                send_http_request(url, payload, headers)

            elif args.mode == "file":
                # Fallback to local file logging
                try:
                    with open(args.file_path, "a", encoding="utf-8") as f:
                        f.write(log_data["raw_event"] + "\n")
                    print(f"[SUCCESS] Appended log to file: {log_data['raw_event']}")
                except Exception as e:
                    print(f"[ERROR] Failed to write file: {e}", file=sys.stderr)

            counter += 1
            if i < args.count - 1:
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n[STOP] Log generation stopped by user.")

    print(f"[SUMMARY] Sent {counter} event(s).")


if __name__ == "__main__":
    main()
