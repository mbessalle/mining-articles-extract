#!/usr/bin/env python3
"""enrich_text_files.py

Updates existing .txt files in the 'projects/' directory by prepending them
with key metadata extracted from their corresponding .json file.

This script is idempotent; it will not add the header if it already exists.

Usage:
    python3 enrich_text_files.py [--dry-run] [--max-files N]

Options:
    --dry-run      : Preview the changes without modifying any files.
    --max-files N  : Process only the first N text files found.
"""

import argparse
import json
import logging
from pathlib import Path

# --- Basic Setup ---
# Use a more detailed format for the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("text_enricher")

# --- Configuration ---
ROOT_DIR = Path("/home/laptop/projects/celis/usa")
PROJECTS_DIR = ROOT_DIR / "projects"

# This is a unique marker to check if a file has already been processed.
METADATA_HEADER_MARKER = "--- Article Metadata ---"


def add_metadata_to_files(dry_run: bool, max_files: int | None):
    """
    Finds all .txt files, reads their .json counterpart, and prepends metadata.
    """
    if not PROJECTS_DIR.is_dir():
        logger.error(f"Projects directory not found: {PROJECTS_DIR}")
        return

    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    if dry_run:
        logger.info("--- DRY RUN ACTIVATED: No files will be modified. ---")

    # Use rglob to find all .txt files recursively, and sort for consistent processing order
    all_txt_files = sorted(list(PROJECTS_DIR.rglob("*.txt")))

    if not all_txt_files:
        logger.warning("No .txt files found to process in the 'projects' directory.")
        return
        
    logger.info(f"Found {len(all_txt_files)} total .txt files.")

    # Apply max_files limit if provided
    files_to_process = all_txt_files[:max_files] if max_files is not None else all_txt_files
    if max_files is not None:
        logger.info(f"Processing a maximum of {max_files} files as requested.")

    for i, txt_path in enumerate(files_to_process, 1):
        # Log which file we are currently working on
        logger.info(f"--- Processing file {i}/{len(files_to_process)}: {txt_path.relative_to(ROOT_DIR)} ---")

        # 1. Check if the file has already been updated
        original_content = txt_path.read_text(encoding="utf-8")
        if METADATA_HEADER_MARKER in original_content:
            logger.info(f"  -> RESULT: SKIPPED (Already contains metadata header)")
            skipped_count += 1
            continue
            
        # 2. Find the corresponding JSON file
        json_path = txt_path.with_suffix('.json')
        if not json_path.exists():
            logger.warning(f"  -> RESULT: ERROR (Corresponding JSON file not found: {json_path.name})")
            error_count += 1
            continue

        # 3. Read and parse the JSON file
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            article_data = data.get('article', {})
            
            # Extract required fields with fallbacks
            project_name = article_data.get('project_name', data.get('project_name', 'N/A'))
            company_name = article_data.get('company_name', data.get('company_name', 'N/A'))
            primary_commodity = article_data.get('primary_commodity', data.get('primary_commodity', 'N/A'))
            exchange = article_data.get('exchange', data.get('exchange', 'N/A'))
            root_ticker = article_data.get('root_ticker', data.get('root_ticker', 'N/A'))

            # 4. Create the formatted metadata header
            metadata_header = f"""{METADATA_HEADER_MARKER}
Project Name: {project_name}
Company Name: {company_name}
Exchange: {exchange}
Ticker: {root_ticker}
Primary Commodity: {primary_commodity}
------------------------"""

            # 5. Combine header with original content
            new_content = f"{metadata_header}\n\n{original_content}"

            # 6. Write back to the file or simulate for dry run
            if dry_run:
                logger.info(f"  -> RESULT: [DRY RUN] Would prepend metadata to {txt_path.name}")
            else:
                try:
                    txt_path.write_text(new_content, encoding="utf-8")
                    logger.info(f"  -> RESULT: UPDATED (Successfully prepended metadata)")
                except Exception as e:
                    logger.error(f"  -> RESULT: ERROR (Failed to write to {txt_path.name}: {e})")
                    error_count += 1
                    continue
            
            updated_count += 1

        except json.JSONDecodeError:
            logger.error(f"  -> RESULT: ERROR (Could not parse JSON file: {json_path.name})")
            error_count += 1
        except Exception as e:
            logger.error(f"  -> RESULT: ERROR (An unexpected error occurred: {e})")
            error_count += 1

    logger.info("="*30)
    logger.info("--- Enrichment Summary ---")
    log_prefix = "Would update" if dry_run else "Updated"
    logger.info(f"{log_prefix}: {updated_count} files")
    logger.info(f"Skipped (already enriched): {skipped_count} files")
    logger.info(f"Errors (missing JSON, etc.): {error_count} files")
    logger.info("="*30)


def main():
    """Parses command-line arguments and runs the enricher."""
    parser = argparse.ArgumentParser(
        description="Prepends .txt files with metadata from corresponding .json files.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the changes without modifying any files."
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Limit the process to the first N .txt files found."
    )
    args = parser.parse_args()
    
    logger.info("Starting text file enrichment process...")
    add_metadata_to_files(dry_run=args.dry_run, max_files=args.max_files)
    logger.info("Enrichment process finished.")


if __name__ == "__main__":
    main()