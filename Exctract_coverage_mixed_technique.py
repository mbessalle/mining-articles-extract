#!/usr/bin/env python3
import os
import pathlib
import base64
import logging
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
KEYWORDS = ["hectare", "ha", "km2", "square kilometer", "square kilometre", "km²", "area", "tenement", "exploration", "license", "licence", "permit", "EPM", "EL", "tenure", "ground", "coverage"]

def process_pdf(pdf_path, client, project_name):
    """Process a PDF file to extract coverage area information using keyword-focused approach."""
    try:
        # Read the PDF file
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
        
        # Encode the PDF content as base64
        pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
        
        # First prompt: Search for keywords
        keyword_prompt = f"""
        FIRST TASK: Search this PDF for the following keywords related to land area: {', '.join(KEYWORDS)}
        
        For each keyword found, note:
        1. The page number
        2. The location on the page (top, middle, bottom, header, footer)
        3. A brief context (20-50 words surrounding the keyword)
        
        Return your findings in this format:
        "KEYWORD_RESULTS:
        - Found 'hectare' on page 1, top: "project covers 5,000 hectares of prospective ground"
        - Found 'km2' on page 2, footer: "total area of 150 km2 across three tenements"
        etc."
        
        If no keywords are found, return "KEYWORD_RESULTS: No keywords found"
        """
        
        # Call the Gemini API for keyword search
        keyword_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a document analysis specialist searching for specific keywords related to land area and project coverage. MAKE SURE THE COVERAGE IS OF THE PROJECT AND NOT SOME OTHER PROJECT BEING DISCUSSED IN THE DOCUMENT! IMPORTANT!"},
                {"role": "user", "content": [
                    {"type": "text", "text": keyword_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
                ]}
            ],
            temperature=0.0,
            max_tokens=800,
        )
        
        # Extract the keyword results
        keyword_results = keyword_response.choices[0].message.content.strip()
        logger.info(f"Keyword search results: {keyword_results}")
        
        # If no keywords found, return None
        if "No keywords found" in keyword_results:
            return None
        
        # Second prompt: Extract coverage area data based on keyword locations
        coverage_prompt = f"""
        SECOND TASK: Based on the keyword locations I found, extract the coverage area information for the {project_name} project.
        
        Here are the keyword locations:
        {keyword_results}
        
        I need to know the total area covered by the project in hectares (ha). If the area is given in square kilometers (km²), 
        please convert it to hectares (1 km² = 100 ha).
        
        Look for patterns like:
        - "X hectares"
        - "X ha"
        - "X km²" or "X square kilometers"
        - "area of X"
        - "covering X"
        - "X of ground"
        - "tenement/license/permit area of X"
        
        Focus on the areas where the keywords were found. If multiple area values are mentioned, try to identify the TOTAL project area.
        
        Return the information in this format:
        "COVERAGE_HECTARES: [number]"
        
        Include ONLY the number (convert to hectares if needed). For example: "COVERAGE_HECTARES: 5000"
        If you find "150 km²", convert it to hectares and return "COVERAGE_HECTARES: 15000"
        
        If the information is not found, return "COVERAGE_HECTARES: NOT FOUND"
        
        Also provide the exact text where you found this information:
        "SOURCE_TEXT: [exact text from the document]"
        """
        
        # Call the Gemini API for coverage area extraction
        coverage_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a mining project data extraction specialist focused on finding land area measurements."},
                {"role": "user", "content": [
                    {"type": "text", "text": coverage_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
                ]}
            ],
            temperature=0.0,
            max_tokens=300,
        )
        
        # Extract the coverage data result
        coverage_result = coverage_response.choices[0].message.content.strip()
        logger.info(f"Coverage area extraction result: {coverage_result}")
        
        # Parse the coverage data
        coverage_data = {}
        
        # Extract coverage hectares
        if "COVERAGE_HECTARES:" in coverage_result:
            hectares_line = [line for line in coverage_result.split("\n") if "COVERAGE_HECTARES:" in line][0]
            hectares = hectares_line.split("COVERAGE_HECTARES:")[1].strip()
            if hectares != "NOT FOUND":
                try:
                    # Try to convert to float, handling commas in numbers
                    hectares_clean = hectares.replace(',', '')
                    coverage_data["coverage_hectares"] = float(hectares_clean)
                except ValueError:
                    logger.warning(f"Could not convert '{hectares}' to float")
                    coverage_data["coverage_hectares"] = hectares
        
        # Extract source text
        if "SOURCE_TEXT:" in coverage_result:
            source_line = coverage_result.split("SOURCE_TEXT:")[1].strip()
            coverage_data["source_text"] = source_line
        
        if coverage_data:
            return coverage_data
        
        return None
        
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {e}")
        return None

def update_csv_with_coverage_data(results):
    """Update the CSV file with the extracted coverage area data."""
    try:
        # Load the CSV file
        df = pd.read_csv("data/raw/coverage_hectares.csv")
        
        # Create a backup of the original file
        df.to_csv("data/raw/coverage_hectares_backup.csv", index=False)
        logger.info(f"Original file backed up to data/raw/coverage_hectares_backup.csv")
        
        # Update the dataframe with the extracted coverage data
        updated_count = 0
        for article_id, coverage_data in results.items():
            # Find the row for this article
            idx = df[df["article_id"] == article_id].index
            if len(idx) > 0:
                # Update the row with available data
                if "coverage_hectares" in coverage_data:
                    df.loc[idx, "coverage_hectares"] = coverage_data["coverage_hectares"]
                    updated_count += 1
                if "source_text" in coverage_data:
                    df.loc[idx, "source_text"] = coverage_data["source_text"]
        
        # Save the updated dataframe
        df.to_csv("data/raw/coverage_hectares_updated.csv", index=False)
        logger.info(f"Updated {updated_count} projects with coverage area data")
        logger.info(f"Updated CSV file saved to data/raw/coverage_hectares_updated.csv")
        
        # Find projects that still have missing or zero data
        missing_data = df[(df["coverage_hectares"].isna()) | (df["coverage_hectares"] == 0)]
        
        # Extract project names
        missing_projects = missing_data["project_name"].tolist()
        missing_articles = missing_data["article_id"].tolist()
        
        logger.info(f"\nStill missing coverage data for {len(missing_projects)} projects")
        
        return missing_articles, missing_projects
        
    except Exception as e:
        logger.error(f"Error updating CSV file: {e}")
        return [], []

def normalize_project_name(name):
    """Normalize project names for comparison."""
    # Convert to lowercase
    name = name.lower()
    # Replace spaces and special characters with underscores
    name = re.sub(r'[^a-z0-9]', '_', name)
    return name

def find_project_directory(project_name):
    """Find the project directory based on the project name."""
    # Extract the base project name (without 'Project' suffix)
    base_name = project_name.replace(" Project", "").strip()
    
    # Normalize the project name
    normalized_name = normalize_project_name(base_name)
    
    # Special cases for project names that don't match directory names
    special_cases = {
        "bullabulling": "bullabulling_project",
        "mulline": "mulline_project",
        "whiteheads": "whiteheads_project",
        # Add more special cases as needed
    }
    
    if normalized_name in special_cases:
        normalized_name = special_cases[normalized_name]
    
    # Base directory for projects
    base_dir = pathlib.Path("/home/moises/celis/analisis-datos-mineria/projects")
    
    # Try to find an exact match
    for project_dir in base_dir.iterdir():
        if project_dir.is_dir():
            if normalize_project_name(project_dir.name) == normalized_name:
                return project_dir
    
    # If no exact match, try to find a directory that contains the project name
    for project_dir in base_dir.iterdir():
        if project_dir.is_dir():
            if normalized_name in normalize_project_name(project_dir.name):
                return project_dir
    
    # If still no match, try to find a directory where the project name contains the directory name
    for project_dir in base_dir.iterdir():
        if project_dir.is_dir():
            if normalize_project_name(project_dir.name) in normalized_name:
                return project_dir
    
    # If no match found, return None
    return None


def find_pdf_files(project_dir):
    """Find PDF files in the project directory."""
    if project_dir is None:
        return []
    
    pdf_files = []
    for file_path in project_dir.glob("**/*.pdf"):
        pdf_files.append(file_path)
    
    return pdf_files


def find_article_pdf(article_id):
    """Find the PDF file for a specific article ID."""
    # Extract the article number from the article_id (e.g., 'article_1' -> '1')
    article_num = article_id.split('_')[1] if '_' in article_id else article_id
    
    # Check in the pdfs directory
    pdf_path = pathlib.Path(f"/home/moises/celis/analisis-datos-mineria/pdfs/article_{article_num}.pdf")
    
    if pdf_path.exists():
        return pdf_path
    
    return None


def main():
    """Main function to extract coverage area data from PDFs."""
    # Load environment variables
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY environment variable not set")
        return
    
    # Initialize Gemini client
    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai"
    )
    
    # Load the coverage hectares CSV file
    try:
        coverage_df = pd.read_csv("data/raw/coverage_hectares.csv")
    except Exception as e:
        logger.error(f"Error loading coverage_hectares.csv: {e}")
        return
    
    # Find projects with missing or zero coverage data
    missing_data = coverage_df[(coverage_df["coverage_hectares"].isna()) | 
                              (coverage_df["coverage_hectares"] == 0)]
    
    # Extract article IDs and project names
    missing_articles = missing_data["article_id"].tolist()
    missing_projects = missing_data["project_name"].tolist()
    
    logger.info(f"Found {len(missing_projects)} projects with missing coverage data")
    
    # Process projects in batches to manage API rate limits
    batch_size = 5
    results = {}
    
    for i in range(0, len(missing_articles), batch_size):
        batch_articles = missing_articles[i:i+batch_size]
        batch_projects = missing_projects[i:i+batch_size]
        
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(missing_articles)-1)//batch_size + 1}")
        
        for article_id, project_name in zip(batch_articles, batch_projects):
            logger.info(f"Processing {article_id}: {project_name}")
            
            # Find the PDF file for this article
            pdf_path = find_article_pdf(article_id)
            
            if pdf_path is None:
                # If article PDF not found, try to find the project directory and PDFs
                project_dir = find_project_directory(project_name)
                if project_dir is None:
                    logger.warning(f"Could not find directory for project: {project_name}")
                    continue
                
                pdf_files = find_pdf_files(project_dir)
                if not pdf_files:
                    logger.warning(f"No PDF files found for project: {project_name}")
                    continue
                
                # Process each PDF file until we find coverage data
                for pdf_path in pdf_files:
                    logger.info(f"Processing PDF: {pdf_path}")
                    coverage_data = process_pdf(pdf_path, client, project_name)
                    
                    if coverage_data is not None:
                        results[article_id] = coverage_data
                        logger.info(f"Found coverage data for {project_name}: {coverage_data}")
                        break
            else:
                # Process the article PDF
                logger.info(f"Processing article PDF: {pdf_path}")
                coverage_data = process_pdf(pdf_path, client, project_name)
                
                if coverage_data is not None:
                    results[article_id] = coverage_data
                    logger.info(f"Found coverage data for {project_name}: {coverage_data}")
        
        # Update the CSV file after each batch
        if results:
            missing_articles, missing_projects = update_csv_with_coverage_data(results)
    
    logger.info("Processing complete")


if __name__ == "__main__":
    main()
