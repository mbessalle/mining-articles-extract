"""clean_json_descriptions.py

Batch script to walk through all JSON files in usa/projects,
convert the HTML stored in the description field into plain text for easier
LLM processing, and store it back under a new key `description_text`.

Usage:
    python clean_json_descriptions.py [--overwrite]

If --overwrite is given, the original `description` field will be replaced by
its cleaned text. Otherwise the script adds a sibling field `description_text`
leaving original HTML intact.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT_DIR / "projects"


def html_to_text(html: str) -> str:
    """Convert HTML to plaintext using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # get_text with separator ensures paragraphs separated
    return soup.get_text(" ", strip=True)


def process_json(path: Path, overwrite: bool = False) -> None:
    try:
        data: Dict[str, Any]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️  Failed to load {path}: {e}")
        return

    # Locate description
    desc_html = None
    if isinstance(data, dict):
        if "description" in data and isinstance(data["description"], str):
            desc_html = data["description"]
        elif "article" in data and isinstance(data["article"], dict):
            desc_html = data["article"].get("description")
            if desc_html is not None and not isinstance(desc_html, str):
                desc_html = None

    if not desc_html:
        # nothing to clean
        return

    desc_text = html_to_text(desc_html)

    if overwrite:
        # Replace in place where found
        if "description" in data:
            data["description"] = desc_text
        elif "article" in data and "description" in data["article"]:
            data["article"]["description"] = desc_text
    else:
        # additive
        if "article" in data and isinstance(data["article"], dict):
            data["article"]["description_text"] = desc_text
        else:
            data["description_text"] = desc_text

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✔ Cleaned {path}")
    except Exception as e:
        print(f"⚠️  Failed to write {path}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean description HTML in project JSON files.")
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional list of JSON files to process. If omitted, the entire projects directory is scanned.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace original description html with text instead of adding description_text key",
    )
    args = parser.parse_args()

    if args.files:
        json_files = [Path(f) for f in args.files]
    else:
        if not PROJECTS_DIR.exists():
            print(f"Projects directory {PROJECTS_DIR} does not exist.")
            sys.exit(1)
        json_files = list(PROJECTS_DIR.rglob("*.json"))
        print(f"Found {len(json_files)} json files to process…")

    for path in json_files:
        process_json(path, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
