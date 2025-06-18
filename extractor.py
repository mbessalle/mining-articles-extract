#!/usr/bin/env python3
import os
import json
import logging
import re
from pathlib import Path
from typing import Iterable, Dict, Tuple
import dotenv
from openai import OpenAI
from tqdm import tqdm

# --- Configuration ---
dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
MODEL_NAME = "gemini-2.5-pro-preview-06-05"
SCRIPT_DIR = Path(__file__).resolve().parent
# We will define ROOT_DIR and PROJECTS_DIR inside main() for better scope management.

RULE_FILES = [
    SCRIPT_DIR / "extraction-rules-core-logic.md",
    SCRIPT_DIR / "extraction-rules-edge-cases.md",
]
METADATA_HEADER_MARKER = "--- Article Metadata ---"
METADATA_FOOTER_MARKER = "------------------------"


# --- Helper Functions (No changes here) ---

def load_rules(rule_files: Iterable[Path]) -> str:
    """Loads and combines rule files into a single system prompt."""
    logger.info("Loading extraction rules...")
    combined_rules = ""
    for file_path in rule_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                combined_rules += f.read() + "\n---\n"
            logger.info(f"Successfully loaded rule file: {file_path}")
        except FileNotFoundError:
            logger.error(f"CRITICAL ERROR: Rule file not found at {file_path}. Exiting.")
            exit(1)
    
    system_prompt = f"""
You are a meticulous data synthesis engine specializing in mining and M&A announcements.
Your task is to analyze a collection of documents related to a single project and synthesize the information into ONE SINGLE, CONSOLIDATED JSON object.

You MUST adhere to the following rules, which are composed of core logic and edge cases.
Failure to follow these rules, especially the justification requirements, will result in an incorrect output.

--- START OF RULES ---
{combined_rules}
--- END OF RULES ---

Your output MUST be a single, valid JSON object that strictly conforms to the schema defined in the rules.
Do not include any explanatory text, markdown formatting, or anything else outside of the JSON object itself.
For every field, you must provide both a `value` and a `justification` as specified.
"""
    return system_prompt

def parse_text_file(file_path: Path) -> Tuple[Dict[str, str], str]:
    """
    Parses an enriched .txt file, separating the metadata header from the body.
    Returns: (metadata_dictionary, body_text_string)
    """
    content = file_path.read_text(encoding="utf-8")
    metadata = {}
    body = content

    if METADATA_HEADER_MARKER in content:
        try:
            parts = content.split(METADATA_FOOTER_MARKER, 1)
            header_text = parts[0]
            body = parts[1].strip() if len(parts) > 1 else ""

            pattern = re.compile(r"^\s*([^:]+?)\s*:\s*(.*)$", re.MULTILINE)
            for match in pattern.finditer(header_text):
                key = match.group(1).strip().lower().replace(" ", "_")
                value = match.group(2).strip()
                metadata[key] = value
        except Exception as e:
            logger.warning(f"Could not parse metadata block in {file_path.name}, using full text. Error: {e}")
            body = content
            metadata = {}

    return metadata, body

def synthesize_data_from_texts(client: OpenAI, system_prompt: str, combined_text: str, authoritative: Dict[str, str]) -> Dict | None:
    """
    Calls the LLM API to synthesize a single structured data object from combined texts.
    """
    auth_lines = []
    project_name = authoritative.get("project_name", "Unknown Project")

    for key, value in authoritative.items():
        if value and value != 'N/A':
            display_key = "ticker and exchange" if key in ['exchange', 'root_ticker'] else key.replace('_', ' ')
            auth_lines.append(f"The authoritative {display_key} for this project is **{value}**.")
    
    auth_block = "\n".join(auth_lines)

    user_prompt = f"""
    The primary project of interest for this analysis is: **{project_name.upper()}**

    You have been provided with the following authoritative metadata parsed from the source file. Use it to guide your extraction.
    {auth_block}

    You will now be given the combined text from all available source documents for this single project. Your task is to analyze ALL of this text to produce ONE SINGLE, CONSOLIDATED JSON output that best represents the details for the **{project_name.upper()}** project ONLY.

    --- COMBINED DOCUMENT TEXT START ---
    {combined_text}
    --- COMBINED DOCUMENT TEXT END ---
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        response_content = response.choices[0].message.content
        extracted_data = json.loads(response_content)
        return extracted_data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from LLM response for project {project_name}: {e}\nLLM Response: {response_content}")
        return None
    except Exception as e:
        logger.error(f"An API call error occurred for project {project_name}: {e}")
        return None

# --- Main Execution Logic ---

def main():
    """
    Orchestrates data synthesis by processing all .txt files within each project folder.
    """
    # *** THE FIX IS HERE: Define paths inside the main function ***
    ROOT_DIR = SCRIPT_DIR
    PROJECTS_DIR = ROOT_DIR / "projects"

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("CRITICAL ERROR: GOOGLE_API_KEY environment variable not set.")
        return
    client = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai")
    
    system_prompt = load_rules(RULE_FILES)

    if not PROJECTS_DIR.is_dir():
        logger.error(f"Projects directory not found at '{PROJECTS_DIR}'. Exiting.")
        return

    project_dirs = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
    if not project_dirs:
        logger.warning("No project subdirectories found to process. Exiting.")
        return

    logger.info(f"Found {len(project_dirs)} projects to process.")

    for project_dir in tqdm(sorted(project_dirs), desc="Processing Projects"):
        project_name = project_dir.name
        logger.info(f"--- Starting Synthesis for Project: {project_name} ---")
        
        txt_files = sorted(list(project_dir.glob("*.txt")))
        if not txt_files:
            logger.warning(f"No .txt files found in '{project_name}'. Skipping.")
            continue
            
        all_body_content = []
        authoritative_metadata = {}
        source_file_paths = [str(p.relative_to(ROOT_DIR)) for p in txt_files]

        for txt_path in txt_files:
            metadata, body = parse_text_file(txt_path)
            all_body_content.append(body)
            
            if not authoritative_metadata and metadata:
                logger.info(f"Sourcing authoritative metadata from: {txt_path.name}")
                authoritative_metadata = {
                    "project_name": metadata.get("project_name", project_name.replace("_", " ")),
                    "company_name": metadata.get("company_name"),
                    "primary_commodity": metadata.get("primary_commodity"),
                    "exchange": metadata.get("exchange"),
                    "root_ticker": metadata.get("ticker"),
                }

        if not authoritative_metadata:
            authoritative_metadata['project_name'] = project_name.replace("_", " ")
            logger.warning(f"No metadata headers found for project {project_name}. Using folder name as project name.")
            
        combined_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_body_content)
        
        consolidated_json = synthesize_data_from_texts(client, system_prompt, combined_text, authoritative_metadata)

        final_output = {
            "source_files": source_file_paths,
            "extraction_data": consolidated_json or "ERROR: FAILED_TO_PROCESS"
        }
        
        output_file_path = project_dir / f"results_{project_name}.json"
        try:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_output, f, indent=2, ensure_ascii=False)
            
            status = "Successfully synthesized and saved" if consolidated_json else "Failed to synthesize, error log saved"
            # Now this line will work because ROOT_DIR is defined in the same scope.
            logger.info(f"--- Finished Project: {project_name}. {status} to {output_file_path.relative_to(ROOT_DIR)} ---")
        except Exception as e:
            logger.error(f"Failed to save results for project '{project_name}': {e}")
            
    logger.info("All projects have been processed.")

if __name__ == "__main__":
    main()