#!/usr/bin/env python3
import os
import json
import logging
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# --- Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
MODEL_NAME = "gemini-2.5-pro-preview-06-05"
PROJECTS_DIR = Path("golden_data")
RULE_FILES = ["extraction-rules-core-logic.md", "extraction-rules-edge-cases.md"]

# --- Helper Functions ---

def load_rules(rule_files: list[str]) -> str:
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

def get_project_name_from_path(file_path: Path) -> str:
    """Derives the project name from the file path stem."""
    filename_stem = file_path.stem
    parts = filename_stem.split('_')
    if parts and parts[-1].isdigit():
        return '_'.join(parts[:-1])
    return filename_stem

def synthesize_data_from_texts(client: OpenAI, system_prompt: str, combined_text: str, project_name: str) -> dict | None:
    """
    Calls the LLM API to synthesize a single structured data object from combined texts.
    """
    # This prompt is now specifically designed for synthesis and includes the project name for context.
    user_prompt = f"""
    The primary project of interest for this analysis is: **{project_name.upper()}**

    You will be given the combined text from multiple source documents for a single project.
    Your task is to analyze ALL of this combined text to produce ONE SINGLE, CONSOLIDATED JSON output that best represents the details for the **{project_name.upper()}** project ONLY.

    - Adhere to RULE #1 (DATA RELEVANCE) above all others. If a data point is for a different project or is a combined total for multiple projects, you MUST NOT use it unless a specific sub-rule (like the 'Shared Commitments' rule) tells you how to process it.
    - For each field in the schema, find the most accurate or most recent information from across all the provided documents that pertains ONLY to the **{project_name.upper()}** project.

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
        logger.error(f"Failed to decode JSON from LLM response: {e}\nLLM Response: {response_content}")
        return None
    except Exception as e:
        logger.error(f"An API call error occurred: {e}")
        return None

def main():
    """
    Main function to orchestrate the data synthesis process, saving one
    consolidated result file for each project.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("CRITICAL ERROR: GOOGLE_API_KEY environment variable not set.")
        return
    client = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai")
    
    system_prompt = load_rules(RULE_FILES)

    logger.info(f"Scanning for .txt files in '{PROJECTS_DIR}' and grouping by project...")
    all_text_files = list(PROJECTS_DIR.rglob("*.txt"))
    
    project_files = defaultdict(list)
    for file_path in all_text_files:
        project_name = get_project_name_from_path(file_path)
        if project_name:
            project_files[project_name].append(file_path)
    
    if not project_files:
        logger.warning("No project text files found to process. Exiting.")
        return
    
    logger.info(f"Found {len(project_files)} projects to process.")

    for project_name, files_in_project in tqdm(project_files.items(), desc="Processing Projects"):
        logger.info(f"--- Starting Synthesis for Project: {project_name} ({len(files_in_project)} files) ---")
        
        all_content = []
        source_file_paths_str = []
        
        for file_path in sorted(files_in_project):
            try:
                content = file_path.read_text(encoding='utf-8')
                all_content.append(content)
                source_file_paths_str.append(str(file_path.relative_to(PROJECTS_DIR.parent)))
            except Exception as e:
                logger.error(f"Could not read file {file_path}: {e}")
        
        if not all_content:
            logger.warning(f"No content found for project '{project_name}'. Skipping.")
            continue
            
        combined_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_content)

        # Pass the project_name to the synthesis function for crucial context
        consolidated_json = synthesize_data_from_texts(client, system_prompt, combined_text, project_name)

        final_output = {
            "source_files": source_file_paths_str,
            "extraction_data": consolidated_json or "ERROR: FAILED_TO_PROCESS"
        }
        
        try:
            output_dir = files_in_project[0].parent 
            output_file_path = output_dir / f"results_{project_name}.json"
            
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_output, f, indent=2, ensure_ascii=False)
            
            status = "Successfully synthesized and saved" if consolidated_json else "Failed to synthesize, error log saved"
            logger.info(f"--- Finished Project: {project_name}. {status} to {output_file_path} ---")

        except Exception as e:
            logger.error(f"Failed to save results for project '{project_name}': {e}")
            
    logger.info("All projects have been processed.")

if __name__ == "__main__":
    main()