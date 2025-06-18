#!/usr/bin/env python3
"""organize_files.py

Moves scraped .txt files from a flat directory ('scraped_text/') into the
appropriate, pre-existing project folders inside the 'projects/' directory.

It matches files based on their ID, assuming a file like '27700.txt' belongs
in the same folder as '27700.json'.

Usage:
    python3 organize_files.py [--dry-run] [--max-files N]

Options:
    --dry-run      : Preview the file moves without actually changing anything.
    --max-files N  : Process only the first N files found.
"""

import argparse
import re
from pathlib import Path
import logging

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("file_organizer")

# --- Configuration ---
ROOT_DIR = Path("/home/laptop/projects/celis/usa")
SOURCE_DIR = ROOT_DIR / "scraped_text"
DEST_ROOT_DIR = ROOT_DIR / "projects"

# Regex to extract the numeric ID from a filename like '12345.json' or '12345.txt'
FILENAME_ID_RE = re.compile(r"^(\d+)\.(json|txt)$")


def build_article_to_folder_map(base_dir: Path) -> dict[str, Path]:
    """
    Scans the directory structure to build a map of:
    { 'article_id': Path_to_its_project_folder }
    e.g., {'27700': Path('/.../projects/Alta_Mesa_ISR')}
    """
    lookup = {}
    logger.info("Indexing existing project directories and files...")
    if not base_dir.is_dir():
        logger.error(f"Destination root directory not found at: {base_dir}")
        return lookup

    for json_file in base_dir.rglob("*.json"):
        match = FILENAME_ID_RE.search(json_file.name)
        if match:
            lookup[match.group(1)] = json_file.parent
            
    logger.info(f"✔ Indexed {len(lookup)} unique article files in their destination folders.")
    return lookup


def organize_text_files(dry_run: bool, max_files: int | None):
    """
    Moves files from the source directory to their mapped destination,
    respecting dry-run and max-files settings.
    """
    if not SOURCE_DIR.is_dir():
        logger.error(f"Source directory not found: {SOURCE_DIR}")
        return

    article_map = build_article_to_folder_map(DEST_ROOT_DIR)
    if not article_map:
        logger.warning("No articles indexed. Cannot organize files. Aborting.")
        return

    moved_count = 0
    skipped_count = 0
    unmatched_count = 0
    processed_count = 0

    if dry_run:
        logger.info("--- DRY RUN ACTIVATED: No files will be moved. ---")

    logger.info(f"Scanning '{SOURCE_DIR.name}' for .txt files to organize...")

    # Get a list of files to process
    files_to_process = sorted(list(SOURCE_DIR.glob("*.txt")))
    
    # Apply the max_files limit if specified
    if max_files is not None:
        logger.info(f"Processing a maximum of {max_files} files.")
        files_to_process = files_to_process[:max_files]

    for txt_file in files_to_process:
        processed_count += 1
        match = FILENAME_ID_RE.search(txt_file.name)
        if not match:
            continue

        article_id = match.group(1)
        dest_folder = article_map.get(article_id)

        if dest_folder:
            dest_path = dest_folder / txt_file.name
            
            if dest_path.exists():
                logger.warning(f"Skipping '{txt_file.name}': a file already exists at '{dest_folder.relative_to(ROOT_DIR)}'.")
                skipped_count += 1
                continue

            # Perform the move or simulate it
            log_prefix = "[DRY RUN] Would move" if dry_run else "Moved"
            logger.info(f"{log_prefix} '{txt_file.name}' -> '{dest_path.relative_to(ROOT_DIR)}'")
            
            if not dry_run:
                try:
                    txt_file.rename(dest_path)
                except OSError as e:
                    logger.error(f"Could not move '{txt_file.name}'. Error: {e}")
                    # Don't increment moved_count if it fails
                    continue
            
            moved_count += 1
        else:
            logger.warning(f"No destination folder found for article ID '{article_id}' ({txt_file.name}). Leaving file in place.")
            unmatched_count += 1
            
    logger.info("--- Organization Complete ---")
    logger.info(f"Files Scanned: {processed_count}")
    log_prefix = "Would move" if dry_run else "Moved"
    logger.info(f"{log_prefix}: {moved_count} files")
    logger.info(f"Skipped (already exist): {skipped_count} files")
    logger.info(f"Unmatched (no destination): {unmatched_count} files")


def main():
    """Parses command-line arguments and runs the organizer."""
    parser = argparse.ArgumentParser(
        description="Moves scraped .txt files into their corresponding project folders.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview file moves without actually performing them."
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Limit the process to the first N files found in the source directory."
    )
    args = parser.parse_args()
    
    organize_text_files(dry_run=args.dry_run, max_files=args.max_files)


if __name__ == "__main__":
    main()