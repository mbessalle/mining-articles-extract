import os
import shutil
import re
from pathlib import Path

# --- CONFIGURATION ---
# The main directory where all your raw project data is stored.
SOURCE_PROJECTS_DIR = Path('projects')
# The directory where your 'golden.json' files are, and where we'll copy the .txt files to.
GOLDEN_DATA_DIR = Path('golden_data')

# --- SCRIPT ---
print("--- Starting script to copy source .txt files to golden_data folders ---")

if not SOURCE_PROJECTS_DIR.is_dir():
    print(f"ERROR: Source directory '{SOURCE_PROJECTS_DIR}' not found. Please make sure it exists.")
    exit(1)

if not GOLDEN_DATA_DIR.is_dir():
    print(f"ERROR: Golden data directory '{GOLDEN_DATA_DIR}' not found.")
    print("Please run the 'split_master_json.py' script first to create it.")
    exit(1)

# Get a list of project names from the folders inside golden_data
# This is our "to-do" list.
golden_project_folders = [d for d in GOLDEN_DATA_DIR.iterdir() if d.is_dir()]

if not golden_project_folders:
    print("WARNING: No project folders found in 'golden_data'. Nothing to do.")
    exit(0)

# We need to match folder names. The source uses underscores, the golden data uses hyphens or original names.
# We'll create a mapping to handle this.
# Example: source 'broken_hill_east' should match golden 'Broken Hill East'
def normalize_for_matching(name):
    return name.lower().replace('_', '').replace('-', '').replace(' ', '')

source_folder_map = {normalize_for_matching(d.name): d for d in SOURCE_PROJECTS_DIR.iterdir() if d.is_dir()}

total_files_copied = 0
projects_processed = 0

for golden_folder in golden_project_folders:
    normalized_golden_name = normalize_for_matching(golden_folder.name)
    
    # Find the matching source folder
    source_folder = source_folder_map.get(normalized_golden_name)

    if not source_folder:
        print(f"WARNING: No matching source folder found in '{SOURCE_PROJECTS_DIR}' for '{golden_folder.name}'. Skipping.")
        continue

    print(f"\nProcessing project: '{golden_folder.name}'")
    print(f"  > Source: {source_folder}")
    print(f"  > Destination: {golden_folder}")
    
    files_in_source = list(source_folder.glob('*.txt'))
    
    if not files_in_source:
        print(f"  > No .txt files found in '{source_folder}'.")
        continue

    for txt_file_path in files_in_source:
        # We only want to copy the article files, not the other json files
        # The pattern seems to be projectname_number.txt. Let's use that to be safe.
        # This regex matches a name ending in an underscore, then one or more digits, then .txt
        if re.search(r'_\d+\.txt$', txt_file_path.name):
            destination_path = golden_folder / txt_file_path.name
            try:
                shutil.copy2(txt_file_path, destination_path)
                print(f"    - Copied '{txt_file_path.name}'")
                total_files_copied += 1
            except Exception as e:
                print(f"    - FAILED to copy '{txt_file_path.name}': {e}")
    
    projects_processed += 1

print("\n--- SCRIPT COMPLETE ---")
print(f"Processed {projects_processed} project folders.")
print(f"Copied a total of {total_files_copied} .txt files.")
print("Your 'golden_data' directory is now ready for the training workflow.")