#!/usr/bin/env python3
"""
Script to extract resources for all commodities associated with each project.
This is a modified version of extract_resource_with_gemini.py that specifically
handles projects with multiple commodities.
"""

# Import necessary libraries
import os                # For file and directory operations
import re                # For regular expressions (pattern matching)
import csv               # For reading CSV files
import json              # For reading/writing JSON files
import time              # For adding delays between API calls
import base64            # For encoding PDF files for API calls
import pathlib           # For handling file paths in a platform-independent way
import logging           # For logging information, warnings, and errors
from dotenv import load_dotenv  # For loading environment variables from .env file
from openai import OpenAI        # OpenAI API client
import sys

# Configure logging to both file and console
# This helps track what the script is doing and diagnose any issues
logging.basicConfig(
    level=logging.INFO,  # Set logging level to INFO (will capture INFO, WARNING, ERROR, CRITICAL)
    format='[%(levelname)s] %(message)s',  # Format of log messages
)

# Load environment variables from .env file (contains API keys)
load_dotenv()

# Define constants used throughout the script
PROJECTS_DIR = 'projects'  # Directory containing project folders
CSV_FILE_PATH = 'data/raw/australia_cleaned.csv'  # Path to the CSV file with project data
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_PDF_SIZE_MB = 18
MAX_PROJECT_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 5

# Rate limiting protection
REQUEST_DELAY_SECONDS = 3  # Add delay between requests to avoid rate limits
PROJECT_DELAY_SECONDS = 10  # Delay between projects

# Dry run mode - when True, no files will be modified
DRY_RUN = False

# Define the prompt template for the OpenAI API
PROMPT_TEMPLATE = """
Analyze the content of the provided PDF document.
Extract mineral resource information for the specified target commodities: {commodities}.

Output the extracted information as a CSV string. The CSV should have the following header row:
resource_value,source_sentence,resource_context,target_commodity,is_project_total

Each subsequent row should represent a distinct resource entry.
- resource_value: The quantitative measure of the resource (e.g., '1.5 Mt @ 2.5% Cu', '710 Million KG H2'). Must include tonnage and grade when applicable. Include contained metal if available.
- source_sentence: The exact sentence from the document that contains the resource_value. For tabular data, include the entire table row or relevant section.
- resource_context: Additional context for the resource, like the deposit name, resource category (Inferred, Indicated, Measured, P50, P90, P10), or relevant table/figure references.
- target_commodity: The primary commodity this resource entry refers to (e.g., Au, Cu, Li, H, H2, He).
- is_project_total: Set to 'yes' if this resource represents the total project resource, 'no' otherwise. Look for phrases like 'total project', 'project resource', 'total resource', or other indicators that this is the overall project resource rather than a specific deposit or zone.

IMPORTANT NOTES:
1. For hydrogen (H or H2) and helium (He) resources, look for values expressed in kg, million kg, bcf, tcf, or similar units.
2. Pay special attention to resource tables that may contain P50 (median), P90 (low), or P10 (high) estimates.
3. For resources with multiple estimates (e.g., P50, P90, P10), extract all of them as separate entries.
4. The largest estimate (typically P50 or mid-case) should be marked as is_project_total='yes'.
5. CRITICAL: Thoroughly scan the document for any tables or sections mentioning resources, especially for hydrogen and helium. These may appear in tables with rows for different gases and columns for different probability estimates.
6. For resources presented in tabular format, make sure to extract ALL values, even if they don't follow the typical resource reporting format.
7. If you see a table like this:
   Resources    Low (P90)    Mid (P50)    High (P10)
   Hydrogen KG  67 Million   710 Million  4.1 Billion
   Helium Bcf   17           97           499
   
   Extract each value as a separate resource entry, with the Mid (P50) value marked as is_project_total='yes'.

Use a comma (,) as the delimiter. Enclose fields in double quotes (") if they contain commas or newline characters.
If no relevant information is found for the target commodities, return just the header row.

Example output:
resource_value,source_sentence,resource_context,target_commodity,is_project_total
"1.5 Mt @ 2.5% Cu","The deposit contains an indicated resource of 1.5 Mt @ 2.5% Cu.","Main Zone - Indicated Resource",Cu,no
"25.3 Mt @ 0.8 g/t Au","Total measured and indicated resources are 25.3 Mt @ 0.8 g/t Au containing 650,000 oz.","JORC Compliant - M&I Resource",Au,yes
"710 Million KG","Resources Low (P90) Mid (P50) High (P10) Hydrogen KG 67 Million 710 Million 4.1 Billion","Rickerscote Prospect - P50 Estimate",H2,yes
"67 Million KG","Resources Low (P90) Mid (P50) High (P10) Hydrogen KG 67 Million 710 Million 4.1 Billion","Rickerscote Prospect - P90 Estimate",H2,no
"4.1 Billion KG","Resources Low (P90) Mid (P50) High (P10) Hydrogen KG 67 Million 710 Million 4.1 Billion","Rickerscote Prospect - P10 Estimate",H2,no
"""

RETRY_PROMPT_ADDENDUM = """
Previous attempts failed to produce valid CSV or verifiable data. 
Please ensure the output is a valid CSV string, starting with the header row: 
resource_value,source_sentence,resource_context,target_commodity,is_project_total
Follow standard CSV quoting rules (double quotes for fields with commas or newlines). Focus on accuracy and completeness.

Remember to identify which resource represents the total project resource by setting is_project_total to 'yes' for that entry.

Pay special attention to tables containing resource information, especially for hydrogen (H2) and helium (He). For example, if you see a table like:

Resources    Low (P90)    Mid (P50)    High (P10)
Hydrogen KG  67 Million   710 Million  4.1 Billion
Helium Bcf   17           97           499

You should extract each value as a separate resource entry.

flourite and caF2 are the same thing
"""

# --- Logging Setup ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- Constants ---
TABLE_KEYWORDS = ["table", "fig.", "figure", "exhibit", "appendix"]

# --- Helper Functions ---
def load_openai_client() -> OpenAI:
    load_dotenv()
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    if not gemini_api_key:
        logger.error("GOOGLE_API_KEY not found in .env file. Please ensure it's set.")
        sys.exit("Exiting: GOOGLE_API_KEY not configured.")
    
    return OpenAI(
        api_key=gemini_api_key,
        base_url=GEMINI_API_BASE_URL,
    )

def normalize_project_name(name):
    """
    Normalize project names for comparison by converting to lowercase,
    replacing spaces and special characters with underscores.
    """
    # Convert to lowercase
    name = name.lower()
    # Replace spaces and special characters with underscores
    name = re.sub(r'[^a-z0-9]', '_', name)
    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Remove leading/trailing underscores
    name = name.strip('_')
    return name

def get_project_commodities():
    """
    Read the CSV file and create a mapping of project names to their commodities.
    Returns a dictionary with normalized project names as keys and lists of commodities as values.
    """
    project_commodities = {}
    
    try:
        with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                project_name = row.get('Project Name', '').strip()
                if not project_name:
                    continue
                
                commodities_raw = row.get('Commodities', '').strip()
                if not commodities_raw:
                    continue
                
                # Split commodities on various separators
                commodities_list = []
                temp_split = re.split(r'[,;/&+]', commodities_raw)
                for item in temp_split:
                    cleaned_item = item.strip().strip('"')
                    if cleaned_item:
                        commodities_list.append(cleaned_item)
                
                if commodities_list:
                    normalized_name = normalize_project_name(project_name)
                    project_commodities[normalized_name] = {
                        'commodities_str': commodities_raw,
                        'commodities': commodities_list
                    }
    
    except FileNotFoundError:
        logger.error(f"CSV file not found: {CSV_FILE_PATH}")
    except Exception as e:
        logger.error(f"Error reading CSV file {CSV_FILE_PATH}: {e}")
    
    return project_commodities

def parse_csv_response(response_text: str, filename: str):
    """
    Parse the CSV response from the OpenAI API.
    
    This function takes the raw CSV text returned by the API and converts it into a list of
    structured resource objects that can be stored in JSON format.
    
    Args:
        response_text: The raw CSV text returned by the API
        filename: The name of the PDF file that was processed (for reference)
        
    Returns:
        A list of dictionaries, each representing a resource entry with standardized fields
    """
    try:
        # Check if the response is empty or just contains the header row (no actual data)
        if not response_text or response_text.strip() == "resource_value,source_sentence,resource_context,target_commodity,is_project_total":
            logger.warning(f"No resource data found in {filename}")
            return []
        
        # Parse the CSV response into individual resources
        resources = []
        lines = response_text.strip().split('\n')
        
        # Skip the header row and process only data rows
        if len(lines) > 1:
            header = lines[0]  # Store header for reference (not used currently)
            data_rows = lines[1:]
            
            # Custom CSV parsing to handle quoted fields with commas
            # This is more robust than using the csv module for potentially malformed CSV
            for row in data_rows:
                fields = []
                in_quotes = False  # Track if we're inside a quoted field
                current_field = ""
                
                # Process each character in the row
                for char in row:
                    if char == '"':  # Toggle quote status
                        in_quotes = not in_quotes
                    elif char == ',' and not in_quotes:  # Field separator (only if not in quotes)
                        fields.append(current_field)
                        current_field = ""
                    else:  # Regular character - add to current field
                        current_field += char
                
                # Add the last field (after the last comma)
                fields.append(current_field)
                
                # Create a structured resource entry if we have all required fields
                if len(fields) >= 5:
                    resource_entry = {
                        "resource_value": fields[0].strip('"'),  # The actual resource value/measurement
                        "source_sentence": fields[1].strip('"'),  # The sentence from the PDF containing this value
                        "resource_context": fields[2].strip('"'),  # Additional context about the resource
                        "target_commodity": fields[3].strip('"'),  # Which commodity this resource refers to (Au, Cu, etc.)
                        "is_project_total": fields[4].strip('"').lower() == 'yes',  # Whether this is the total project resource
                        "filename": os.path.basename(filename)  # Source PDF filename for reference
                    }
                    resources.append(resource_entry)
        
        return resources
    
    except Exception as e:
        logger.error(f"Error parsing CSV response: {e}")
        return []

def verify_extraction(resource_value: str, source_sentence: str, resource_context: str):
    """
    Verify if the extracted resource information is valid and meets quality criteria.
    
    This function performs several checks to ensure that the extracted resource information
    is meaningful and likely to be a genuine resource statement rather than just random text.
    
    Args:
        resource_value: The extracted resource value (e.g., "1.5 Mt @ 2.5% Cu")
        source_sentence: The sentence from which the resource was extracted
        resource_context: Additional context about the resource
        
    Returns:
        Boolean indicating whether the extraction passes validation checks
    """
    # Basic validation - ensure we have the minimum required fields
    if not resource_value or not source_sentence:
        return False
    
    # Check 1: Resource value must contain numeric information
    # Resources always include quantities, so this is a basic requirement
    has_numbers = bool(re.search(r'\d', resource_value))
    if not has_numbers:
        return False
    
    # Check 2: Resource value should contain common resource units or indicators
    # This list covers most common units and terms used in resource reporting
    resource_indicators = [
        # Weight/mass units
        'mt', 'kt', 'gt', 'oz', 'mlb', 'moz', 'koz', 'tonnes', 'tons', 'pounds', 'ounces',
        # Concentration units
        'g/t', '%', 'ppm', 'ppb', 
        # Resource terminology
        'contained', 'resource', 'reserve', 'inferred', 'indicated',
        'measured', 'jorc', 'ni 43-101', 
        # Gas/hydrogen specific units
        'bcf', 'tcf', 'kg', 'million', 'billion'
    ]
    
    # Check if any of the resource indicators appear in the resource value
    has_resource_indicator = any(indicator in resource_value.lower() for indicator in resource_indicators)
    if not has_resource_indicator:
        return False
    
    # Check 3: Verify that source_sentence contains similar numeric information to resource_value
    # Extract all numbers from both the resource value and source sentence
    resource_numbers = re.findall(r'\d+(?:\.\d+)?', resource_value)
    source_numbers = re.findall(r'\d+(?:\.\d+)?', source_sentence)
    
    # Both should contain numbers
    if not resource_numbers or not source_numbers:
        return False
    
    # Check if at least one number from resource_value appears in source_sentence
    # This helps verify that the resource value was actually derived from the source sentence
    number_match = any(num in source_numbers for num in resource_numbers)
    if not number_match:
        return False
    
    # All checks passed
    return True

def call_openai_compatible_gemini_api(pdf_path: pathlib.Path, client: OpenAI, commodities_string: str, attempt_num: int = 1):
    """Call Gemini API with the EXACT commodities string."""
    try:
        # Check file size
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_PDF_SIZE_MB:
            logger.warning(f"PDF file {pdf_path} is too large: {file_size_mb:.2f} MB > {MAX_PDF_SIZE_MB} MB limit")
            return None
        
        # Read and encode the PDF content to base64
        with open(pdf_path, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Prepare the prompt
        prompt = PROMPT_TEMPLATE.format(commodities=commodities_string)
        if attempt_num > 1:
            prompt += RETRY_PROMPT_ADDENDUM
        
        # Make the API call - IMPORTANT: Use image_url type with data URI for PDF
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
                ]}
            ],
            temperature=0.2,
        )
        
        # Extract and return the response text
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            logger.error(f"Empty response from Gemini API for {pdf_path}")
            return None
    
    except Exception as e:
        logger.error(f"Error calling Gemini API for {pdf_path}: {e}")
        return None

def process_pdf_file(pdf_path: pathlib.Path, client: OpenAI, commodities_string: str, max_attempts: int = 2):
    """
    Process a single PDF file with retry logic, using EXACT commodities string.
    In dry run mode, returns mock data instead of making actual API calls.
    """
    # In dry run mode, return mock data instead of making API calls
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would process PDF file: {pdf_path.name} for commodities: {commodities_string}")
        
        # Create mock resources based on the commodities
        # In dry run mode, we'll generate just one resource per commodity per PDF
        # to avoid creating duplicates
        mock_resources = []
        
        # Use a set to track which commodities we've already processed for this PDF
        processed_commodities = set()
        
        for commodity in commodities_string.split(','):
            commodity = commodity.strip()
            if not commodity or commodity in processed_commodities:
                continue
                
            # Create a mock resource for this commodity
            mock_resource = {
                "resource_value": f"10.5 Mt @ 1.2 g/t {commodity}" if commodity in ['Au', 'Ag'] else f"15.3 Mt @ 2.4% {commodity}",
                "source_sentence": f"The project contains an inferred resource of 10.5 Mt @ 1.2 g/t {commodity}.",
                "resource_context": f"Mock data for {pdf_path.stem} - Inferred Resource",
                "target_commodity": commodity,
                "is_project_total": True,
                "filename": pdf_path.name
            }
            mock_resources.append(mock_resource)
            processed_commodities.add(commodity)
            
        logger.info(f"[DRY RUN] Generated {len(mock_resources)} mock resources for {pdf_path.name}")
        return mock_resources
    
    # Normal processing with API calls when not in dry run mode
    for attempt in range(1, max_attempts + 1):
        logger.info(f"Processing {pdf_path.name} (Attempt {attempt}/{max_attempts})")
        
        try:
            # Call the Gemini API
            response_text = call_openai_compatible_gemini_api(pdf_path, client, commodities_string, attempt)
            
            if not response_text:
                logger.warning(f"No response from API for {pdf_path.name}, attempt {attempt}")
                if attempt < max_attempts:
                    logger.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    time.sleep(RETRY_DELAY_SECONDS)
                continue
            
            # Parse the CSV response
            resources = parse_csv_response(response_text, pdf_path.name)
            
            # Verify the extracted resources
            verified_resources = []
            for resource in resources:
                if verify_extraction(
                    resource["resource_value"],
                    resource["source_sentence"],
                    resource["resource_context"]
                ):
                    verified_resources.append(resource)
                else:
                    logger.warning(f"Resource extraction verification failed for {pdf_path.name}: {resource}")
            
            if verified_resources:
                logger.info(f"Successfully extracted {len(verified_resources)} resources from {pdf_path.name}")
                return verified_resources
            else:
                logger.warning(f"No verified resources extracted from {pdf_path.name}, attempt {attempt}")
                if attempt < max_attempts:
                    logger.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    time.sleep(RETRY_DELAY_SECONDS)
        
        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}, attempt {attempt}: {e}")
            if attempt < max_attempts:
                logger.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                time.sleep(RETRY_DELAY_SECONDS)
    
    logger.error(f"Failed to extract resources from {pdf_path.name} after {max_attempts} attempts")
    return []

def process_project_directory(project_name: str, project_dir: pathlib.Path, client: OpenAI, commodities_info: dict, target_commodities=None):
    """
    Process a project directory to extract resources for all or specific commodities.
    
    This function is the core of the resource extraction process. It handles:
    1. Determining which commodities to extract resources for
    2. Processing all PDF files in the project directory
    3. Saving the extracted resources to a JSON file, either creating a new file
       or updating an existing one with new resources
    
    Args:
        project_name: The name of the project directory
        project_dir: Path object pointing to the project directory
        client: The OpenAI client for making API calls
        commodities_info: Dictionary containing information about the project's commodities
        target_commodities: Optional list of specific commodities to target (if None, all commodities are processed)
    """
    logger.info(f"Processing project directory: {project_name}")
    
    # Get the commodities for this project from the commodities_info dictionary
    commodities_string = commodities_info.get('commodities_str', '')  # Original comma-separated string from CSV
    commodities_list = commodities_info.get('commodities', [])        # List of individual commodities
    
    # Verify we have at least one commodity to process
    if not commodities_list:
        logger.warning(f"No commodities found for project {project_name}")
        return
    
    # FILTERING STEP: If target_commodities is provided, only process those specific commodities
    # This is used when we already have resources for some commodities and only need to extract the missing ones
    if target_commodities:
        logger.info(f"Project {project_name} - targeting specific commodities: {target_commodities}")
        # Create a filtered list of commodities that are both in the project's list and in the target list
        filtered_commodities = [c for c in commodities_list if c in target_commodities]
        if not filtered_commodities:
            logger.warning(f"No matching target commodities found for project {project_name}")
            return
        # Create a new comma-separated string with only the target commodities
        commodities_string = ", ".join(filtered_commodities)
        # Use the filtered list for further processing
        commodities_to_process = filtered_commodities
    else:
        # Process all commodities for this project
        logger.info(f"Project {project_name} has commodities: {commodities_string}")
        commodities_to_process = commodities_list
    
    # Find all PDF files in the project directory to process
    pdf_files = list(project_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF files found in {project_dir}")
        return
    
    logger.info(f"Found {len(pdf_files)} PDF files in {project_dir}")
    
    # EXTRACTION STEP: Process each PDF file to extract resources
    all_extracted_resources = []  # Will hold all extracted resources from all PDFs
    for pdf_file in pdf_files:
        logger.info(f"Processing PDF file: {pdf_file.name}")
        # Extract resources from this PDF file for the specified commodities
        resources = process_pdf_file(pdf_file, client, commodities_string, MAX_PROJECT_ATTEMPTS)
        all_extracted_resources.extend(resources)  # Add the extracted resources to our collection
        
        # Add a delay between API calls to avoid rate limiting
        time.sleep(REQUEST_DELAY_SECONDS)
        
    # CONSOLIDATION STEP: Keep only one resource per commodity (preferring project totals and largest resources)
    # This ensures we only have one entry per commodity per project
    new_resources = []
    processed_commodities = set()
    
    # Helper function to extract numeric tonnage from resource value for comparison
    def extract_tonnage(resource_value):
        try:
            # Extract numbers from the resource value
            import re
            numbers = re.findall(r'[\d,\.]+', resource_value)
            if not numbers:
                return 0
            # Convert the first number to float (removing commas)
            return float(numbers[0].replace(',', ''))
        except Exception:
            return 0
    
    # First pass: Look for resources marked as project_total=True
    # If multiple project_total=True resources exist for a commodity, select the largest one
    commodity_to_project_totals = {}
    
    for resource in all_extracted_resources:
        commodity = resource.get('target_commodity', '')
        if not commodity:
            continue
            
        if resource.get('is_project_total', False):
            if commodity not in commodity_to_project_totals:
                commodity_to_project_totals[commodity] = []
            commodity_to_project_totals[commodity].append(resource)
    
    # Add the largest project_total resource for each commodity
    for commodity, resources in commodity_to_project_totals.items():
        if resources:
            # Sort by tonnage (largest first)
            largest_resource = max(resources, key=lambda r: extract_tonnage(r.get('resource_value', '')))
            new_resources.append(largest_resource)
            processed_commodities.add(commodity)
    
    # Second pass: For commodities without a project_total, find the largest resource
    for commodity in commodities_to_process:
        if commodity not in processed_commodities:
            # Find all resources for this commodity
            commodity_resources = [r for r in all_extracted_resources 
                                if r.get('target_commodity', '') == commodity]
            
            if commodity_resources:
                # Sort by tonnage (largest first)
                largest_resource = max(commodity_resources, 
                                      key=lambda r: extract_tonnage(r.get('resource_value', '')))
                new_resources.append(largest_resource)
                processed_commodities.add(commodity)
    
    logger.info(f"Consolidated to {len(new_resources)} resources (one per commodity)")
    # Log details of selected resources
    for resource in new_resources:
        logger.info(f"Selected resource for {resource.get('target_commodity', '')}: {resource.get('resource_value', '')} (Project Total: {resource.get('is_project_total', False)})")

    
    
    # SAVING STEP: Save the extracted resources to a JSON file
    if new_resources:  # Only proceed if we found any resources
        # Check if there are existing resource JSON files in the project directory
        resources_files = list(project_dir.glob("*_resources.json"))
        
        # CASE 1: There is at least one existing resources file to update
        if resources_files:
            # Use the first resources file found (there should typically be only one)
            resources_file = resources_files[0]
            logger.info(f"Found existing resources file: {resources_file.name}")
            
            # Try to read and update the existing resources file
            try:
                # Read the existing resources from the file
                with open(resources_file, 'r') as f:
                    existing_resources = json.load(f)
                    
                # Create a copy of the existing resources to build our updated list
                combined_resources = existing_resources.copy()
                
                # DEDUPLICATION: Add only new resources that don't duplicate existing ones
                added_count = 0
                for new_resource in new_resources:
                    # Check if this resource is already in the existing resources
                    is_duplicate = False
                    for existing_resource in existing_resources:
                        # Consider it a duplicate if both commodity and resource value match
                        if (new_resource.get('target_commodity') == existing_resource.get('target_commodity') and
                            new_resource.get('resource_value') == existing_resource.get('resource_value')):
                            is_duplicate = True
                            break
                    
                    # If it's not a duplicate, add it to the combined resources
                    if not is_duplicate:
                        combined_resources.append(new_resource)
                        added_count += 1
                
                # In dry run mode, just log what would happen without writing to file
                if DRY_RUN:
                    logger.info(f"[DRY RUN] Would add {added_count} new resources to existing file {resources_file.name}")
                    # Print the resources that would be added
                    if added_count > 0:
                        logger.info("[DRY RUN] Resources that would be added:")
                        for i, resource in enumerate([r for r in new_resources if not any(r.get('target_commodity') == er.get('target_commodity') and 
                                                                                        r.get('resource_value') == er.get('resource_value') 
                                                                                        for er in existing_resources)]):
                            logger.info(f"[DRY RUN]   {i+1}. {resource.get('target_commodity')}: {resource.get('resource_value')}")
                else:
                    # Write the combined resources back to the original file
                    with open(resources_file, 'w') as f:
                        json.dump(combined_resources, f, indent=2)
                    logger.info(f"Added {added_count} new resources to existing file {resources_file.name}")
            
            # ERROR HANDLING: If updating the existing file fails, create a new file as fallback
            except Exception as e:
                logger.error(f"Error updating existing resources file {resources_file.name}: {e}")
                # Create a new file with a different name to avoid overwriting the original
                fallback_file = project_dir / f"{project_name}_resources_new.json"
                
                if DRY_RUN:
                    logger.info(f"[DRY RUN] Would save {len(new_resources)} resources to fallback file {fallback_file.name}")
                else:
                    with open(fallback_file, 'w') as f:
                        json.dump(new_resources, f, indent=2)
                    logger.info(f"Saved {len(new_resources)} resources to fallback file {fallback_file.name}")
        
        # CASE 2: No existing resources file, create a new one
        else:
            # Create a new resources file with the standard naming convention
            resources_file = project_dir / f"{project_name}_resources.json"
            
            if DRY_RUN:
                logger.info(f"[DRY RUN] Would create new file {resources_file.name} with {len(new_resources)} resources")
                # Print a sample of the resources that would be saved
                sample_size = min(3, len(new_resources))
                if sample_size > 0:
                    logger.info(f"[DRY RUN] Sample of resources that would be saved (showing {sample_size} of {len(new_resources)}):")
                    for i, resource in enumerate(new_resources[:sample_size]):
                        logger.info(f"[DRY RUN]   {i+1}. {resource.get('target_commodity')}: {resource.get('resource_value')}")
            else:
                with open(resources_file, 'w') as f:
                    json.dump(new_resources, f, indent=2)
                logger.info(f"Saved {len(new_resources)} resources to new file {resources_file.name}")
    else:
        # No resources were extracted from any of the PDF files
        logger.warning(f"No resources extracted for project {project_name}")
    
    # Add a delay between processing different projects
    time.sleep(PROJECT_DELAY_SECONDS)

def main():
    """
    Main function that orchestrates the entire resource extraction process.
    
    This function performs the following steps:
    1. Initializes the OpenAI client for API calls
    2. Reads the CSV file to get all projects and their commodities
    3. Filters to focus only on projects with multiple commodities
    4. For each multi-commodity project:
       a. Finds the corresponding project directory
       b. Checks if resources for some commodities are already extracted
       c. Identifies which commodities still need resource extraction
       d. Processes the project to extract resources for missing commodities
    """
    # STEP 1: Initialize the OpenAI client for API calls
    client = load_openai_client()
    
    # STEP 2: Read the CSV file to get all projects and their commodities
    logger.info("Reading project commodities from CSV file...")
    project_commodities = get_project_commodities()
    
    # STEP 3: Filter to focus only on projects with multiple commodities including gold (Au)
    # We're specifically interested in projects that have gold plus other commodities
    multi_commodity_projects = {}
    for project_name, commodities_info in project_commodities.items():
        commodities = commodities_info['commodities']
        # Check if this project has multiple commodities AND includes gold
        if len(commodities) > 1 and 'Au' in commodities:
            multi_commodity_projects[project_name] = commodities_info
    
    logger.info(f"Found {len(multi_commodity_projects)} projects with gold and other commodities")
    
    # STEP 4: Process each multi-commodity project
    for normalized_name, commodities_info in multi_commodity_projects.items():
        # STEP 4a: Find the corresponding project directory
        # The directory name might not exactly match the project name in the CSV,
        # so we use normalized names for comparison
        project_dirs = [d for d in os.listdir(PROJECTS_DIR) if normalize_project_name(d) == normalized_name]
        
        # Skip if no matching directory is found
        if not project_dirs:
            logger.warning(f"No matching directory found for project {normalized_name}")
            continue
        
        # Get the full path to the project directory
        project_dir = pathlib.Path(PROJECTS_DIR) / project_dirs[0]
        
        # STEP 4b: Check if the project already has resources extracted
        # Look for any JSON files that might contain resource information
        resources_files = list(project_dir.glob("*_resources.json"))
        
        # Default to processing all commodities unless we find some are already covered
        missing_commodities = None
        
        # If resources files exist, check which commodities are already covered
        if resources_files:
            logger.info(f"Project {project_dirs[0]} already has resources file(s): {[f.name for f in resources_files]}")
            
            # STEP 4c: Identify which commodities already have resources extracted
            # Read all existing resource files to build a set of commodities that already have data
            existing_commodities = set()
            for resources_file in resources_files:
                try:
                    with open(resources_file, 'r') as f:
                        resources = json.load(f)
                        for resource in resources:
                            # Add each commodity that has at least one resource entry
                            existing_commodities.add(resource.get('target_commodity', ''))
                except Exception as e:
                    logger.error(f"Error reading resources file {resources_file}: {e}")
            
            # Determine which commodities are missing resource information
            missing_commodities = [c for c in commodities_info['commodities'] if c not in existing_commodities]
            
            # If all commodities are already covered, skip this project
            if not missing_commodities:
                logger.info(f"All commodities already covered for project {project_dirs[0]}")
                continue
            
            logger.info(f"Missing commodities for project {project_dirs[0]}: {missing_commodities}")
        
        # STEP 4d: Process the project directory to extract resources for missing commodities
        # The process_project_directory function will handle the actual extraction and saving
        process_project_directory(project_dirs[0], project_dir, client, commodities_info, missing_commodities)

if __name__ == "__main__":
    # Check if dry run mode is enabled
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract resources for all commodities in projects')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry run mode (no files will be modified)')
    args = parser.parse_args()
    
    # Update dry run flag
    if args.dry_run:
        DRY_RUN = True
        logger.info("=== DRY RUN MODE ENABLED - No files will be modified ===")
    
    main()
