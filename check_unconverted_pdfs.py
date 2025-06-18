#!/usr/bin/env python3
"""check_unconverted_pdfs.py

Scans the 'projects' directory to find all .pdf files that do not have a
corresponding '_pdf.txt' file. This helps identify PDFs that were downloaded
but failed the text extraction/conversion process.

The script prints a clean list grouped by project name.

Usage:
    python3 check_unconverted_pdfs.py
"""

import logging
from pathlib import Path
from collections import defaultdict

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("pdf_checker")

# --- Configuration ---
ROOT_DIR = Path("/home/laptop/projects/celis/usa")
PROJECTS_DIR = ROOT_DIR / "projects"


def find_unconverted_pdfs():
    """
    Finds and reports all .pdf files missing a corresponding _pdf.txt file.
    """
    if not PROJECTS_DIR.is_dir():
        logger.error(f"Projects directory not found: {PROJECTS_DIR}")
        return

    # Use a dictionary to group missing files by project name
    unconverted_map = defaultdict(list)
    total_pdfs_found = 0
    
    logger.info(f"Scanning all subdirectories within '{PROJECTS_DIR}' for PDFs...")

    # Recursively find all .pdf files
    for pdf_path in PROJECTS_DIR.rglob("*.pdf"):
        total_pdfs_found += 1
        
        # Construct the expected path for the corresponding .txt file
        # e.g., '.../76465.pdf' -> '.../76465_pdf.txt'
        expected_txt_path = pdf_path.with_name(f"{pdf_path.stem}_pdf.txt")

        # Check if the text file does NOT exist
        if not expected_txt_path.exists():
            project_name = pdf_path.parent.name
            unconverted_map[project_name].append(pdf_path.name)
            
    logger.info(f"Scan complete. Found {total_pdfs_found} total PDF files.")
    
    # --- Report the results ---
    if not unconverted_map:
        logger.info("✔ All PDFs appear to have been converted to text. No issues found.")
        return
        
    logger.warning("--- Unconverted PDF Report ---")
    logger.warning("The following PDFs were found without a corresponding '_pdf.txt' file:")
    
    total_unconverted = 0
    # Sort by project name for a clean report
    for project_name in sorted(unconverted_map.keys()):
        print(f"\nProject: {project_name}")
        for pdf_filename in unconverted_map[project_name]:
            print(f"  - {pdf_filename}")
            total_unconverted += 1
            
    logger.warning(f"\nTotal Unconverted PDFs: {total_unconverted}")


if __name__ == "__main__":
    find_unconverted_pdfs()