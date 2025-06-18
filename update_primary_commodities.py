"""Add or update `primary_commodity` inside the `article` object of every
<id>.json article file under `usa/projects` using the first commodity listed
for that project in `USA-projects.json`.

Usage:
    python update_primary_commodities.py [--dry-run]

If --dry-run is provided, the script will print the intended modifications
without writing the files.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_CSV_JSON = BASE_DIR / "USA-projects.json"

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

digit_json_re = re.compile(r"^\d+\.json$")


def build_project_commodity_map(path: Path) -> Dict[str, str]:
    """Return mapping of project name -> primary commodity (first listed)."""
    if not path.exists():
        raise FileNotFoundError(f"USA-projects.json not found at {path}")

    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    exported = data.get("Exported Data", [])
    mapping: Dict[str, str] = {}
    for row in exported:
        proj = row.get("Project Name")
        commodities = row.get("Commodities", "")
        if not (proj and commodities):
            continue
        primary = commodities.split(",")[0].strip()
        # Keep the first encountered mapping (assume consistent)
        mapping.setdefault(proj, primary)
    return mapping


def update_article_file(filepath: Path, primary_commodity: str, dry_run: bool = False) -> bool:
    """Insert or update primary_commodity inside article; return True if changed."""
    changed = False
    with filepath.open("r", encoding="utf-8") as fp:
        try:
            data = json.load(fp)
        except json.JSONDecodeError as e:
            logger.warning(f"Skipping {filepath}: invalid JSON ({e})")
            return False

    article_obj: Optional[dict] = data.get("article") if isinstance(data, dict) else None
    if article_obj is None:
        logger.warning(f"Skipping {filepath}: missing 'article' object")
        return False

    # Only update if value differs
    if article_obj.get("primary_commodity") != primary_commodity:
        article_obj["primary_commodity"] = primary_commodity
        changed = True

    if changed and not dry_run:
        with filepath.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.write("\n")  # newline at end of file for POSIX compliance
    return changed


def main():
    parser = argparse.ArgumentParser(description="Populate primary_commodity into article JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes, only report")
    args = parser.parse_args()

    mapping = build_project_commodity_map(PROJECTS_CSV_JSON)
    logger.info(f"Loaded commodities for {len(mapping)} projects from {PROJECTS_CSV_JSON.name}")

    updated_count = 0
    skipped_count = 0
    missing_project_names = set()

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for json_file in project_dir.iterdir():
            if not digit_json_re.match(json_file.name):
                # Ignore results_*.json and others
                continue
            with json_file.open("r", encoding="utf-8") as fp:
                try:
                    temp_data = json.load(fp)
                except json.JSONDecodeError:
                    logger.warning(f"Skipping {json_file}: invalid JSON")
                    skipped_count += 1
                    continue
            # Determine project name from JSON, fall back to directory
            project_name = (
                temp_data.get("project_name")
                or temp_data.get("article", {}).get("project_name")
                or project_dir.name.replace("_", " ")
            )
            primary = mapping.get(project_name)
            if not primary:
                missing_project_names.add(project_name)
                skipped_count += 1
                continue
            if update_article_file(json_file, primary, dry_run=args.dry_run):
                logger.info(f"Updated {json_file.relative_to(BASE_DIR)} -> primary_commodity={primary}")
                updated_count += 1
            else:
                skipped_count += 1

    logger.info(f"Done. Updated {updated_count} files; skipped {skipped_count}.")
    if missing_project_names:
        logger.warning(
            "No commodity info for projects: " + ", ".join(sorted(missing_project_names))
        )


if __name__ == "__main__":
    main()
