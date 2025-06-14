import json
import sys

# --- DETERMINISTIC BUSINESS RULES ---
# These rules are applied consistently to both the agent's output and the golden data.
METER_TO_USD_CONVERSION = 200.0
# NOTE: For a production system, these should be updated periodically or fetched from an API.
EXCHANGE_RATES = {
    'AUD': 0.66,
    'CAD': 0.73,
    'USD': 1.0,
    None: 1.0 # Default to 1.0 (assume USD) if currency is not specified
}

# --- HELPER FUNCTIONS ---
def get_value(data_obj, key):
    """Safely gets the 'value' from a nested object, returning None if any key is missing."""
    return data_obj.get(key, {}).get('value')

def get_justification(data_obj, key):
    """Safely gets the 'justification' from a nested object."""
    return data_obj.get(key, {}).get('justification')

# --- CORE CALCULATION LOGIC ---
def calculate_derived_fields(data_obj):
    """
    Takes a data object with nested raw values and adds final calculated USD fields,
    respecting the financial and area data hierarchies. THIS IS THE DETERMINISTIC ENGINE.
    """
    currency = get_value(data_obj, 'currency') or 'USD'
    conversion_factor = EXCHANGE_RATES.get(currency, 1.0)

    # --- HIERARCHICAL FINANCIAL CALCULATION ---
    # 1. Calculate Share Value (Priority-based)
    share_payments_usd = 0
    if get_value(data_obj, 'share_payments_raw') is not None:
        # Priority 1: Use the explicit raw value if it exists.
        share_payments_usd = (get_value(data_obj, 'share_payments_raw') or 0) * conversion_factor
    elif (get_value(data_obj, 'amount_of_shares_issued') is not None and
          get_value(data_obj, 'issued_share_price') is not None):
        # Priority 2: Calculate from number of shares and price.
        shares = get_value(data_obj, 'amount_of_shares_issued') or 0
        price = get_value(data_obj, 'issued_share_price') or 0
        share_payments_usd = (shares * price) * conversion_factor
    
    # 2. Calculate Cash Value
    cash_payments_usd = (get_value(data_obj, 'cash_payments_raw') or 0) * conversion_factor
    
    # 3. Calculate Exploration Commitment Value
    exp_meters = get_value(data_obj, 'exploration_commitment_meters') or 0
    exp_value_raw = get_value(data_obj, 'exploration_commitment_value_raw') or 0
    total_exploration_usd = (exp_meters * METER_TO_USD_CONVERSION) + (exp_value_raw * conversion_factor)

    # 4. Calculate Aggregate Deal Value (Priority-based)
    aggregate_deal_value_usd = 0
    if get_value(data_obj, 'cash_and_share_payments_combined_raw') is not None:
        # Priority 3: If a combined value is given, it overrides individual components for the aggregate.
        combined_raw = get_value(data_obj, 'cash_and_share_payments_combined_raw') or 0
        aggregate_deal_value_usd = (combined_raw * conversion_factor) + total_exploration_usd
    else:
        # Fallback: Sum the individual components if no combined value exists.
        aggregate_deal_value_usd = cash_payments_usd + share_payments_usd + total_exploration_usd

    # 5. Calculate Standardized Area in Hectares
    area_raw = get_value(data_obj, 'coverage_area_raw')
    area_unit = get_value(data_obj, 'coverage_area_unit')
    coverage_hectares = None
    if area_raw is not None:
        if area_unit and 'km' in str(area_unit).lower():
            coverage_hectares = area_raw * 100 # Convert square kilometers to hectares
        else:
            coverage_hectares = area_raw # Assume hectares if unit is 'ha' or not specified
            
    # --- ADD CALCULATED FIELDS BACK TO OBJECT IN THE CORRECT SCHEMA ---
    data_obj['coverage_hectares'] = {'value': coverage_hectares, 'justification': 'Calculated/Standardized by evaluator.py'}
    data_obj['total_exploration_commitments_usd'] = {'value': total_exploration_usd, 'justification': 'Calculated by evaluator.py'}
    data_obj['aggregate_deal_value_usd'] = {'value': aggregate_deal_value_usd, 'justification': 'Calculated by evaluator.py using financial data hierarchy'}
    
    # 6. Calculate Value per Hectare
    if coverage_hectares and coverage_hectares > 0:
        val_per_ha = data_obj['aggregate_deal_value_usd']['value'] / coverage_hectares
        data_obj['value_per_hectare_usd'] = {'value': val_per_ha, 'justification': 'Calculated by evaluator.py'}
    else:
        data_obj['value_per_hectare_usd'] = {'value': None, 'justification': 'Calculation not possible (no hectares).'}
    
    return data_obj

# --- MAIN EVALUATION FUNCTION ---
def evaluate(generated_file, golden_file):
    try:
        with open(generated_file, 'r', encoding='utf-8') as f:
            generated_data_raw = json.load(f)
        with open(golden_file, 'r', encoding='utf-8') as f:
            golden_data_raw = json.load(f)
    except FileNotFoundError as e:
        print(f"ERROR: Could not find a file. {e}")
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse a JSON file. It might be malformed. {e}")
        return

    # Step 1: Run deterministic calculations on BOTH sets of data to create a level playing field.
    generated_data = calculate_derived_fields(generated_data_raw)
    golden_data = calculate_derived_fields(golden_data_raw)

    # Step 2: Define the COMPLETE list of fields to compare.
    fields_to_compare = [
        # Raw Extracted Fields (Agent's primary task)
        'ceo_buyer', 
        'interest_acquired_percent', 
        'currency', 
        'cash_payments_raw',
        'share_payments_raw', 
        'cash_and_share_payments_combined_raw',
        'amount_of_shares_issued',
        'issued_share_price',
        'exploration_commitment_meters',
        'exploration_commitment_value_raw',
        'exploration_commitment_desc',
        'nsr_acquired_percent',
        'coverage_area_raw',
        'coverage_area_unit',
        'resource_size_desc', 
        'buyer_stock_exchange',
        
        # Final Calculated/Standardized Fields (Result of deterministic logic)
        'coverage_hectares',
        'total_exploration_commitments_usd',
        'aggregate_deal_value_usd',
        'value_per_hectare_usd'
    ]
    
    score = 0
    errors = []

    # Step 3: Loop through and compare each field.
    for key in fields_to_compare:
        gen_val = get_value(generated_data, key)
        gold_val = get_value(golden_data, key)
        
        is_match = False
        # Use a tolerance for floating point comparisons to avoid precision issues.
        if isinstance(gold_val, (float, int)) and gold_val is not None:
            is_match = isinstance(gen_val, (float, int)) and abs(gen_val - gold_val) < 0.01
        elif gold_val is None:
            is_match = gen_val is None
        else:
            is_match = str(gen_val).strip() == str(gold_val).strip()
        
        if is_match:
            score += 1
        else:
            # Create a much more informative error message for the agent to analyze.
            justification = get_justification(generated_data, key)
            error_msg = (f"Field '{key}': FAILED.\n"
                         f"  - Expected: '{gold_val}' (Type: {type(gold_val).__name__})\n"
                         f"  - Got:      '{gen_val}' (Type: {type(gen_val).__name__})\n"
                         f"  - Agent's Justification: '{justification}'")
            errors.append(error_msg)
    
    # Step 4: Print the final report.
    print(f"--- EVALUATION REPORT ---")
    print(f"SCORE: {score}/{len(fields_to_compare)}")
    if errors:
        print("--- ERRORS ---")
        for error in errors:
            print(error)
    else:
        print("--- All compared fields match perfectly! ---")
    print("--- END REPORT ---")
    
    # Save the agent's output enriched with the calculated fields for easy inspection.
    with open(generated_file, 'w', encoding='utf-8') as f:
        json.dump(generated_data, f, indent=4)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python evaluator.py <generated_file.json> <golden_file.json>")
        sys.exit(1)
    generated_file_path = sys.argv[1]
    golden_file_path = sys.argv[2]
    evaluate(generated_file_path, golden_file_path)