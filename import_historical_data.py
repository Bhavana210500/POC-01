#!/usr/bin/env python3
"""
Helix AIOps Platform - Historical Incident Importer
Use this script to import and train the local Machine Learning Model
with your own corporate historical incident data (CSV or JSON formats).

Usage:
  python import_historical_data.py --file your_data.csv --type csv
  python import_historical_data.py --file your_data.json --type json
"""

import argparse
import json
import csv
from pathlib import Path
import sys

# Ensure parent directory is in path for imports
sys.path.insert(0, str(Path(__file__).parent.resolve()))


def import_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of incident objects.")
    return data


def import_csv(filepath):
    incidents = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Map common columns
            incident = {
                "category": row.get("category", "Application"),
                "title": row.get(
                    "title", row.get("short_description", "Unknown Incident")
                ),
                "description": row.get("description", row.get("close_notes", "")),
                "root_cause": row.get("root_cause", row.get("cause", "Unknown Cause")),
                "resolution": row.get("resolution", row.get("resolution_notes", "")),
                "script": row.get(
                    "script", row.get("remediation_script", "app_restart.py")
                ),
            }
            incidents.append(incident)
    return incidents


def main():
    parser = argparse.ArgumentParser(
        description="Import historical incidents to train the Helix AIOps ML engine."
    )
    parser.add_argument(
        "--file", required=True, help="Path to the historical data file."
    )
    parser.add_argument(
        "--type",
        choices=["csv", "json"],
        default=None,
        help="File type (csv or json). If omitted, inferred from extension.",
    )

    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"[ERROR] File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    filetype = args.type or filepath.suffix.lower().replace(".", "")
    if filetype not in ["csv", "json"]:
        print("[ERROR] Unsupported file type. Must be CSV or JSON.", file=sys.stderr)
        sys.exit(1)

    print(f"[START] Reading {filetype.upper()} file: {filepath}")

    try:
        if filetype == "json":
            new_data = import_json(filepath)
        else:
            new_data = import_csv(filepath)

        print(f"[LOADED] Parsed {len(new_data)} incident records from file.")

        # Load existing dataset
        kb_path = Path(__file__).parent / "knowledge_base" / "historical_incidents.json"
        existing_data = []
        if kb_path.exists():
            with open(kb_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)

        # Deduplicate and append
        added_count = 0
        existing_titles = {
            item.get("title", "").lower().strip() for item in existing_data
        }

        for item in new_data:
            # Check basic validation
            if not item.get("title") or not item.get("resolution"):
                continue

            title_clean = item["title"].lower().strip()
            if title_clean not in existing_titles:
                existing_data.append(item)
                existing_titles.add(title_clean)
                added_count += 1

        # Write back
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        with open(kb_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=4)

        print(f"[SUCCESS] Appended {added_count} new unique records to {kb_path}.")
        print("[INFO] Re-training the local NLP vectorizer with the new dataset...")

        # Import and trigger retraining
        from ml_model import ml_model

        ml_model.load_training_data()
        ml_model.train()
        print("[SUCCESS] Machine learning model successfully trained and updated!")

    except Exception as e:
        print(f"[ERROR] Failed to import: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
