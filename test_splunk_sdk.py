import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Load configuration from .env file
load_dotenv(Path(__file__).parent / ".env", override=True)

import splunklib.client as client
import splunklib.results as results


def test_splunk_connection():
    host = (
        os.getenv("SPLUNK_HOST", "https://prd-p-mrttm.splunkcloud.com")
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
    )
    port = int(os.getenv("SPLUNK_PORT", "8089"))
    username = os.getenv("SPLUNK_USERNAME") or "sc_admin"
    password = os.getenv("SPLUNK_PASSWORD") or "your_password_here"

    print(
        f"[*] Initializing Splunk SDK connection to host: {host}:{port} with user: {username} ..."
    )

    try:
        service = client.connect(
            host=host, port=port, username=username, password=password, scheme="https"
        )
        print("[+] SUCCESS: Connected to Splunk Cloud instance via Splunk SDK!")

        query = "search index=main earliest=-5m latest=now | head 10"
        print(f"[*] Dispatching search job: {query}")
        job = service.jobs.create(query)

        while not job.is_done():
            print("[*] Waiting for search job to complete...")
            time.sleep(2)
            job.refresh()

        print("[+] Job complete! Fetching results:")
        for result in results.JSONResultsReader(job.results(output_mode="json")):
            print(result)

    except Exception as e:
        print(f"[-] Splunk SDK Connection Failed: {type(e).__name__}: {e}")
        if "401" in str(e) or "Login failed" in str(e):
            print(
                "\n[!] IMPORTANT: Port 8089 is OPEN and responding! The failure is just an invalid password."
            )
            print(
                "[!] Please enter your real password in the .env file or directly in test_splunk_sdk.py and run again."
            )
        else:
            print("\n[!] NOTE: Port 8089 connection timed out at the firewall level.")


if __name__ == "__main__":
    test_splunk_connection()
