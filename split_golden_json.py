import json
import os
import re
from pathlib import Path

# --- CONFIGURATION ---
MASTER_JSON_PATH = 'golden_data.json'  # The name of your single JSON file
OUTPUT_DIR = Path('golden_data')
PROJECT_NAME_KEY = 'Project Name'  # The key in your JSON that holds the project name

# This maps the messy keys from your source JSON to the clean, simple keys
# we want the agent to work with. This is a critical part of the setup.
FIELD_MAPPING = {
    'Contact/CEO': 'ceo_buyer',
    'Interest Acquired %': 'interest_acquired_percent',
    'Sum of Cash Payments ($)': 'cash_payments_usd',
    'Exploration commitments ($)': 'exploration_commitment_usd',
    'Share price ($)': 'share_price_usd',
    'Number of Shares sold': 'shares_sold',
    'Share Value ($)': 'share_payments_usd',
    'NSR %': 'nsr_acquired_percent',
    'Verified Project Area Ha': 'coverage_hectares',
    'Resource': 'resource_size_desc',
    'Exchange': 'buyer_stock_exchange'
}

# --- HELPER FUNCTIONS ---
def sanitize_filename(name):
    """Removes characters that are invalid for folder names."""
    if not name: return "unnamed_project"
    return re.sub(r'[<>:"/\\|?*]', '_', name.strip())

def clean_numeric(value_str):
    """Extracts the first number from a string, handling commas, percentages, etc."""
    if not isinstance(value_str, str):
        return value_str if isinstance(value_str, (int, float)) else None
    
    # Handle specific non-values
    if value_str.strip() in ['-', '']:
        return None
    
    # Find the first number-like pattern (can be integer or float)
    match = re.search(r'[\d,.]+', value_str)
    if not match:
        return None
        
    try:
        # Clean the matched string and convert to a number
        cleaned_str = match.group(0).replace(',', '')
        if '.' in cleaned_str:
            return float(cleaned_str)
        else:
            return int(cleaned_str)
    except (ValueError, TypeError):
        return None

# --- MAIN SCRIPT ---
print("Starting script to split master JSON into a folder structure...")
OUTPUT_DIR.mkdir(exist_ok=True)

try:
    with open(MASTER_JSON_PATH, 'r', encoding='utf-8') as f:
        master_data = json.load(f)
except FileNotFoundError:
    print(f"ERROR: The file '{MASTER_JSON_PATH}' was not found. Please place it in the project root.")
    exit(1)
except json.JSONDecodeError:
    print(f"ERROR: The file '{MASTER_JSON_PATH}' is not a valid JSON file.")
    exit(1)

# The data is nested under the "golden_data" key
project_list = master_data.get('golden_data', [])

for project_object in project_list:
    project_name = project_object.get(PROJECT_NAME_KEY)
    if not project_name:
        print(f"Skipping record with no '{PROJECT_NAME_KEY}': {project_object}")
        continue

    sanitized_name = sanitize_filename(project_name)
    project_dir = OUTPUT_DIR / sanitized_name
    project_dir.mkdir(exist_ok=True)
    
    json_output_path = project_dir / 'golden.json'
    
    # Build the clean JSON object for this project
    clean_project_data = {}
    for source_key, target_key in FIELD_MAPPING.items():
        raw_value = project_object.get(source_key) # Use .get() to avoid errors on missing keys
        
        # If the key doesn't exist or value is None, store as null
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            clean_project_data[target_key] = None
            continue

        # Clean numeric fields, otherwise store the raw (but stripped) string
        if 'usd' in target_key or 'percent' in target_key or 'hectares' in target_key:
            clean_project_data[target_key] = clean_numeric(raw_value)
        else:
            clean_project_data[target_key] = str(raw_value).strip()

    with open(json_output_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(clean_project_data, jsonfile, indent=2)
        
    print(f"Successfully created: {json_output_path}")

print("\n--- SCRIPT COMPLETE ---")
print("Next step: Copy your source .txt article files into the corresponding, newly created folders inside `golden_data`.")