#!/usr/bin/env python3
"""Populate/overwrite `company_name` in each article JSON with the operator company
from USA-projects.json.

Usage:
  python update_company_name.py [--dry-run]

This mirrors `update_primary_commodities.py` but for the company/operator field.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("update_company_name")

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
USA_JSON_PATH = BASE_DIR / "USA-projects.json"


def build_mapping() -> dict[str, str]:
    """Returns {project_name -> operator_company}"""
    if not USA_JSON_PATH.exists():
        logger.error("USA-projects.json not found at %s", USA_JSON_PATH)
        raise SystemExit(1)

    with USA_JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    mapping: dict[str, str] = {}

    # Handle both plain list and wrapped format with "Exported Data"
    entries = data.get("Exported Data") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        logger.error("Unexpected structure in USA-projects.json – expected list or key 'Exported Data'.")
        raise SystemExit(1)

    for entry in entries:
        # This check prevents crashes from malformed data in the JSON file.
        if not isinstance(entry, dict):
            continue
        proj = entry.get("Project Name")
        # Fallback to Owner Company if Operator is missing
        operator = entry.get("Operator Company") or entry.get("Owner Company")
        if proj and operator:
            # Normalize the key to lowercase to ensure consistent matching
            norm_key = proj.strip().lower()
            mapping.setdefault(norm_key, operator.strip())

    logger.info("Loaded operator companies for %d projects from USA-projects.json", len(mapping))
    return mapping


# Regex to match files like "12345.json"
INT_RE = re.compile(r"^\d+\.json$")


def update_files(mapping: dict[str, str], dry: bool = False) -> None:
    """Iterates through project files, looks up the company, and updates the JSON."""
    updated = 0
    skipped = 0
    missing_projects: list[str] = []
    failure_header_printed = False

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for json_path in project_dir.glob("*.json"):
            if not INT_RE.match(json_path.name):
                continue

            data = json.loads(json_path.read_text(encoding="utf-8"))
            article = data.get("article") if "article" in data else data

            # Get the project name, falling back to the directory name if needed.
            project_name = article.get("project_name") or project_dir.name.replace("__", " ")

            # --- FIX #1: NORMALIZE THE LOOKUP KEY ---
            # The key must be normalized (lowercase, stripped) just like when the map was built.
            normalized_lookup_key = project_name.strip().lower()
            operator_company = mapping.get(normalized_lookup_key)

            if not operator_company:
                # --- FIX #2: PRINT FAILURE POINT IMMEDIATELY ---
                if not failure_header_printed:
                    logger.warning("---POINTS OF FAILURE (File -> Key)---")
                    failure_header_printed = True
                
                logger.warning(
                    "  File: %s\n    -> Failed lookup for project key: '%s'",
                    json_path.relative_to(BASE_DIR),
                    project_name  # Show original name for easier debugging
                )
                
                missing_projects.append(project_name)
                skipped += 1
                continue

            # Check if the update is even needed
            if article.get("company_name") == operator_company:
                skipped += 1
                continue

            # Update the company name in the loaded data
            article["company_name"] = operator_company

            # Write the changes back to the file unless it's a dry run
            if not dry:
                json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            
            updated += 1
            logger.info("Updated %s -> company_name=%s", json_path.relative_to(BASE_DIR), operator_company)

    logger.info("Done. Updated %d files; skipped %d.", updated, skipped)
    if missing_projects:
        uniq = sorted(set(missing_projects))
        logger.warning("---SUMMARY OF MISSING PROJECTS---")
        logger.warning("No operator info for projects: %s", ", ".join(uniq[:10]) + (" ..." if len(uniq) > 10 else ""))


def main():
    """Main function to parse arguments and run the update."""
    parser = argparse.ArgumentParser(description="Inject operator company into article JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    args = parser.parse_args()

    mapping = build_mapping()
    update_files(mapping, dry=args.dry_run)


# --- FIX #3: ENSURE THE SCRIPT EXECUTION BLOCK IS PRESENT ---
# This block is essential for the script to run when called from the command line.
if __name__ == "__main__":
    main()