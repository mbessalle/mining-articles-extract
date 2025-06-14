import json
import re
from pathlib import Path
import sys

# --- CONFIGURATION: Keyword-to-Field Mapping ---
# This is the core logic that connects keywords to the final schema fields.
KEYWORD_MAP = {
    'cash_payments_raw': ['cash', 'payment', '$', 'consideration'],
    'share_payments_raw': ['share', 'shares', 'scrip', 'equity'],
    'cash_and_share_payments_combined_raw': ['cash and scrip', 'cash and shares'],
    'amount_of_shares_issued': ['issue of', 'issued', 'shares will be subject'],
    'issued_share_price': ['price', 'vwap', 'deemed issue price'],
    'exploration_commitment_meters': ['drilling', 'meters', 'metres'],
    'exploration_commitment_value_raw': ['exploration', 'commitment', 'expenditure'],
    'nsr_acquired_percent': ['nsr', 'net smelter return', 'royalty'],
    'coverage_area_raw': ['hectares', 'ha', 'km²', 'tenement'],
    'resource_size_desc': ['resource', 'JORC', 'tonnes', 'ounces', 'oz', 'grade'],
    'ceo_buyer': ['CEO', 'Managing Director', 'Chairman', 'Executive Chair'],
    'interest_acquired_percent': ['interest', 'stake', 'ownership', 'acquire'],
    'currency': ['AUD', 'A$', 'CAD', 'C$', 'USD', 'US$'],
    'buyer_stock_exchange': ['ASX:', 'TSX:', 'TSX-V:', 'CSE:']
}

CONTEXT_WINDOW = 75 # Characters on each side of the keyword to provide as context

def find_keywords(source_text_path: Path):
    """
    Scans a text file for keywords and saves their locations and context to a JSON file.
    """
    locations = {field: [] for field in KEYWORD_MAP}
    
    try:
        with open(source_text_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"ERROR: Source file not found: {source_text_path}")
        return

    for line_num, line in enumerate(lines, 1):
        for field, keywords in KEYWORD_MAP.items():
            for keyword in keywords:
                # Use re.finditer to find all non-overlapping matches in the line
                # The 'i' flag makes it case-insensitive
                for match in re.finditer(re.escape(keyword), line, re.IGNORECASE):
                    start, end = match.span()
                    
                    # Create a context snippet around the keyword
                    context_start = max(0, start - CONTEXT_WINDOW)
                    context_end = min(len(line), end + CONTEXT_WINDOW)
                    context = line[context_start:context_end].strip()
                    
                    locations[field].append({
                        'keyword': keyword,
                        'line': line_num,
                        'context': f"...{context}..."
                    })

    # Remove fields that had no keyword matches
    final_locations = {k: v for k, v in locations.items() if v}
    
    # Save the output to a corresponding .locations.json file
    output_path = source_text_path.with_suffix('.locations.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_locations, f, indent=2)
        
    print(f"Keyword locations saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python keyword_finder.py <path_to_source_text_file>")
        sys.exit(1)
    
    source_path = Path(sys.argv[1])
    # For the workflow, we need to aggregate the text files first.
    # This standalone script will just run on a single file for testing.
    # The workflow will handle aggregation.
    find_keywords(source_path)